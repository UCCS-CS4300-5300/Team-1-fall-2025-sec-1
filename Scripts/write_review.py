import os
import openai
from github import Github

def get_github_instance(github_token):
    """Takes github token to give a GitHub instance"""
    try:
        github_instance = Github(github_token)

        return github_instance    
    except Exception as e:
        raise ValueError(f"An error occurred getting the GitHub instance: {e}")

def get_repo(github_instance, repo_name):
    """Takes github instance and repo name to get an instance of repo"""
    try:
        repo = github_instance.get_repo(repo_name)

        return repo    
    except Exception as e:
        raise ValueError(f"An error occurred getting the repo: {e}")

def get_pull_request(repo, pull_request_number):
    """Gets pull request through repo and issue number of pull request"""
    try:
        pull_request = repo.get_pull(number=pull_request_number)

        return pull_request    
    except Exception as e:
        raise ValueError(f"An error occurred getting the pull request: {e}")

def get_files_from_pull_request(pull_request):
    try:
        info = ""
        for file in pull_request.get_files():
            info += f"File: {file.filename}\n{file.patch}\n\n"

        return info
    except Exception as e:
        raise ValueError(f"Failed to get all files from pull request {e}")

def get_AI_review(info_and_files):
    """Send file and diff info to be reviewed by OpenAI, return its message"""

    # Generates response with OpenAI review as contents based on diff
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an expert code reviewer."},
            {"role": "user", "content": f"""
                You are a senior software engineer reviewing a GitHub Pull Request.
                Provide specific, actionable feedback focused on:
                - Code quality
                - Best practices
                - Potential bugs
                - Readability and maintainability
                - Start out with a score out of 10

                Here is the diff of the PR:
                {info_and_files}
                """
            }
        ],
        max_completion_tokens=2048
    )

    return response.choices[0].message.content

def main():
    """Sets up GitHub variables and uses them to comment an AI review on a PR."""

    # Takes values specified from env in AI_code_review.yml file
    try:
        openai.api_key = os.getenv("OPENAI_API_KEY")

        github_token = os.getenv("GITHUB_TOKEN")
        # If unable to acquire token, raise error
        if not github_token:
            raise ValueError('No GitHub Token')

        repo_name = os.getenv("REPO_NAME")
        # If unable to acquire repo name, raise error
        if not repo_name:
            raise ValueError('No Repo Name Token')

        pull_request_number = int(os.getenv("PR_NUMBER"))
        # If unable to acquire pull request number, raise error
        if not pull_request_number:
            raise ValueError('No Repo Name Token')
    except Exception as e:
        raise ValueError(f"An error occurred: {e}")

    github_instance = get_github_instance(github_token)
    repo_instance = get_repo(github_instance, repo_name)
    pull_request = get_pull_request(repo_instance, pull_request_number)

    files_and_info = get_files_from_pull_request(pull_request)

    pull_request.create_issue_comment(f"Code Review\n\n{get_AI_review(files_and_info)}")


if __name__ == '__main__':
    main()