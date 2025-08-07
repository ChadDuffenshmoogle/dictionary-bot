# /app/src/github_api.py

import logging
import requests

# Fix the import error by using a direct import instead of a relative one.
# The relative import from `.config` was causing the app to crash.
from config import GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH, YOUR_GITHUB_PAT

logger = logging.getLogger('discord')

class GitHubAPI:
    """
    A class to interact with the GitHub API for file management.
    """
    def __init__(self):
        self.headers = {
            "Authorization": f"token {YOUR_GITHUB_PAT}",
            "Accept": "application/vnd.github.v3+json"
        }
        self.base_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/"

    def get_file_sha(self, file_path):
        """
        Gets the SHA of a file from the repository.
        """
        url = self.base_url + file_path
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()['sha']
        return None

    def update_file(self, file_path, content, message):
        """
        Updates a file in the repository with new content.
        """
        sha = self.get_file_sha(file_path)
        if not sha:
            logger.error(f"Failed to get SHA for file: {file_path}")
            return False

        url = self.base_url + file_path
        payload = {
            "message": message,
            "content": content,
            "sha": sha,
            "branch": GITHUB_BRANCH
        }
        response = requests.put(url, headers=self.headers, json=payload)
        if response.status_code == 200:
            logger.info(f"Successfully updated file: {file_path}")
            return True
        else:
            logger.error(f"Failed to update file: {file_path} with status code {response.status_code}. Response: {response.text}")
            return False

    def create_file(self, file_path, content, message):
        """
        Creates a new file in the repository.
        """
        url = self.base_url + file_path
        payload = {
            "message": message,
            "content": content,
            "branch": GITHUB_BRANCH
        }
        response = requests.put(url, headers=self.headers, json=payload)
        if response.status_code == 201:
            logger.info(f"Successfully created file: {file_path}")
            return True
        else:
            logger.error(f"Failed to create file: {file_path} with status code {response.status_code}. Response: {response.text}")
            return False

    def delete_file(self, file_path, message):
        """
        Deletes a file from the repository.
        """
        sha = self.get_file_sha(file_path)
        if not sha:
            logger.error(f"Failed to get SHA for file to delete: {file_path}")
            return False

        url = self.base_url + file_path
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
            logger.error(f"Failed to delete file: {file_path} with status code {response.status_code}. Response: {response.text}")
            return False
