import requests
import base64
from typing import Optional, List
from .config import GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH, YOUR_GITHUB_PAT, logger # Use YOUR_GITHUB_PAT

class GitHubAPI:
    """Handles all GitHub API interactions for the dictionary repository."""

    def __init__(self, token: str):
        self.token = token
        self.owner = GITHUB_OWNER
        self.repo = GITHUB_REPO
        self.base_url = f"https://api.github.com/repos/{self.owner}/{self.repo}"
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }

    def get_file_content(self, filename: str) -> Optional[str]:
        """Gets file content from GitHub."""
        try:
            url = f"{self.base_url}/contents/{filename}"
            response = requests.get(url, headers=self.headers)

            if response.status_code == 200:
                content = response.json()['content']
                return base64.b64decode(content).decode('utf-8')
            elif response.status_code == 404:
                logger.info(f"File {filename} not found on GitHub.")
                return None
            else:
                logger.error(f"GitHub API error getting {filename}: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting file from GitHub: {e}")
            return None

    def create_or_update_file(self, filename: str, content: str, message: str) -> bool:
        """Creates or updates a file on GitHub."""
        try:
            url = f"{self.base_url}/contents/{filename}"
            existing = requests.get(url, headers=self.headers)

            data = {
                "message": message,
                "content": base64.b64encode(content.encode('utf-8')).decode('ascii'),
                "branch": GITHUB_BRANCH
            }

            if existing.status_code == 200:
                data["sha"] = existing.json()["sha"] # Required for updates

            response = requests.put(url, headers=self.headers, json=data)

            if response.status_code in [200, 201]:
                logger.info(f"Successfully uploaded {filename} to GitHub.")
                return True
            else:
                logger.error(f"GitHub API error uploading {filename}: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error uploading file to GitHub: {e}")
            return False

    def list_dictionary_files(self) -> List[str]:
        """Lists all dictionary files in the repo based on naming conventions."""
        try:
            url = f"{self.base_url}/contents"
            response = requests.get(url, headers=self.headers)

            if response.status_code == 200:
                files = response.json()
                from .config import FILE_PREFIX, FILE_EXTENSION # Import here to avoid circular dependency if needed
                dict_files = [
                    f['name'] for f in files
                    if f['type'] == 'file' and
                    f['name'].startswith(FILE_PREFIX) and
                    f['name'].endswith(FILE_EXTENSION)
                ]
                return dict_files
            else:
                logger.error(f"GitHub API error listing files: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error listing files from GitHub: {e}")
            return []
