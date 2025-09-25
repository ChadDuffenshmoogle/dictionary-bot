# src/github_api.py

import logging
import requests
import base64
from typing import List, Optional

# Fix the import by using relative import (correct for package structure)
from .config import GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH, YOUR_GITHUB_PAT

logger = logging.getLogger(__name__)

class GitHubAPI:
    """
    A class to interact with the GitHub API for file management.
    """
    def __init__(self):
        if not YOUR_GITHUB_PAT:
            logger.error("GitHub PAT not found in environment variables")
            raise ValueError("GitHub PAT is required")
            
        self.headers = {
            "Authorization": f"token {YOUR_GITHUB_PAT}",
            "Accept": "application/vnd.github.v3+json"
        }
        self.base_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents"
        logger.info(f"GitHubAPI initialized for {GITHUB_OWNER}/{GITHUB_REPO}")

    def list_dictionary_files(self) -> List[str]:
        """List all dictionary files in the repository with improved error handling."""
        try:
            logger.info(f"Attempting to list files from: {self.base_url}")
            response = requests.get(self.base_url, headers=self.headers, timeout=30)
            
            logger.info(f"GitHub API response status: {response.status_code}")
            
            if response.status_code == 401:
                logger.error("GitHub API returned 401 Unauthorized - check your GitHub token")
                return []
            elif response.status_code == 403:
                logger.error("GitHub API returned 403 Forbidden - check your token permissions")
                return []
            elif response.status_code == 404:
                logger.error(f"GitHub API returned 404 Not Found - check if repo {GITHUB_OWNER}/{GITHUB_REPO} exists")
                return []
            
            response.raise_for_status()
            
            files = response.json()
            logger.info(f"Retrieved {len(files)} total files from GitHub")
            
            # Log all files for debugging
            all_filenames = [file['name'] for file in files]
            logger.info(f"All files in repo: {all_filenames}")
            
            dictionary_files = [
                file['name'] for file in files 
                if file['name'].startswith('UNICYCLIST DICTIONARY') and file['name'].endswith('.txt')
            ]
            
            logger.info(f"Found {len(dictionary_files)} dictionary files: {dictionary_files}")
            
            if not dictionary_files:
                logger.warning("No dictionary files found! This might be why the bot isn't working.")
                logger.warning("Expected files to start with 'UNICYCLIST DICTIONARY' and end with '.txt'")
            
            return dictionary_files
            
        except requests.exceptions.Timeout:
            logger.error("GitHub API request timed out")
            return []
        except requests.exceptions.ConnectionError:
            logger.error("Failed to connect to GitHub API - check your internet connection")
            return []
        except Exception as e:
            logger.error(f"Error listing dictionary files: {e}")
            logger.error(f"Full error details: {type(e).__name__}: {str(e)}")
            return []

    def get_file_content(self, filename: str) -> Optional[str]:
        """Get the content of a file from the repository with improved error handling."""
        try:
            url = f"{self.base_url}/{filename}"
            logger.info(f"Attempting to get content from: {url}")
            
            response = requests.get(url, headers=self.headers, timeout=30)
            
            if response.status_code == 404:
                logger.warning(f"File not found: {filename}")
                # Let's also try to list files again to see what's available
                available_files = self.list_dictionary_files()
                logger.warning(f"Available dictionary files: {available_files}")
                return None
            elif response.status_code == 401:
                logger.error("GitHub API returned 401 Unauthorized when getting file content")
                return None
            elif response.status_code == 403:
                logger.error("GitHub API returned 403 Forbidden when getting file content")
                return None
                
            response.raise_for_status()
            file_data = response.json()
            
            # Decode base64 content
            content = base64.b64decode(file_data['content']).decode('utf-8')
            logger.info(f"Successfully retrieved content for {filename} ({len(content)} characters)")
            return content
            
        except requests.exceptions.Timeout:
            logger.error(f"Timeout getting file content for {filename}")
            return None
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error getting file content for {filename}")
            return None
        except Exception as e:
            logger.error(f"Error getting file content for {filename}: {e}")
            logger.error(f"Full error details: {type(e).__name__}: {str(e)}")
            return None

    def get_file_sha(self, file_path: str) -> Optional[str]:
        """Gets the SHA of a file from the repository."""
        try:
            url = f"{self.base_url}/{file_path}"
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                return response.json()['sha']
            return None
        except Exception as e:
            logger.error(f"Error getting SHA for {file_path}: {e}")
            return None

    def test_connection(self) -> bool:
        """Test the GitHub API connection."""
        try:
            logger.info("Testing GitHub API connection...")
            response = requests.get(self.base_url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                logger.info("✅ GitHub API connection successful")
                return True
            else:
                logger.error(f"❌ GitHub API connection failed with status {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ GitHub API connection test failed: {e}")
            return False

    # ... rest of your methods remain the same ...
    def create_or_update_file(self, file_path: str, content: str, message: str) -> bool:
        """Creates a new file or updates an existing one."""
        try:
            # Encode content to base64
            encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
            
            # Check if file exists to get SHA for update
            sha = self.get_file_sha(file_path)
            
            url = f"{self.base_url}/{file_path}"
            payload = {
                "message": message,
                "content": encoded_content,
                "branch": GITHUB_BRANCH
            }
            
            if sha:
                payload["sha"] = sha
                logger.info(f"Updating existing file: {file_path}")
            else:
                logger.info(f"Creating new file: {file_path}")
            
            response = requests.put(url, headers=self.headers, json=payload)
            
            if response.status_code in [200, 201]:
                logger.info(f"Successfully {'updated' if sha else 'created'} file: {file_path}")
                return True
            else:
                logger.error(f"Failed to {'update' if sha else 'create'} file: {file_path}")
                logger.error(f"Status: {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error creating/updating file {file_path}: {e}")
            return False

    def update_file(self, file_path: str, content: str, message: str) -> bool:
        """Updates a file in the repository with new content."""
        return self.create_or_update_file(file_path, content, message)

    def create_file(self, file_path: str, content: str, message: str) -> bool:
        """Creates a new file in the repository."""
        return self.create_or_update_file(file_path, content, message)

    def delete_file(self, file_path: str, message: str) -> bool:
        """Deletes a file from the repository."""
        try:
            sha = self.get_file_sha(file_path)
            if not sha:
                logger.error(f"Failed to get SHA for file to delete: {file_path}")
                return False

            url = f"{self.base_url}/{file_path}"
            payload = {
                "message": message,
                "sha": sha,
                "branch": GITHUB_BRANCH
            }
            
            response = requests.delete(url, headers=self.headers, json=payload)
            
            if response.status_code == 200:
                logger.info(f"Successfully deleted file: {file_path}")
                return True
            else:
                logger.error(f"Failed to delete file: {file_path}")
                logger.error(f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {e}")
            return False
