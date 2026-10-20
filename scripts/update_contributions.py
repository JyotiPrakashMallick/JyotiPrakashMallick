"""
Fetches GitHub contribution data and updates README.md automatically.
Requires GITHUB_TOKEN env var with read:user and read:org scopes.
"""

import json
import os
import re
import urllib.request

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
USERNAME = "Ansumanbhujabal"
README_PATH = os.path.join(os.path.dirname(__file__), "..", "README.md")

GRAPHQL_URL = "https://api.github.com/graphql"


def graphql(query: str) -> dict:
    data = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=data,
        headers={
            "Authorization": f"bearer {GITHUB_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def fetch_contributions() -> dict:
    query = """
    {
      user(login: "%s") {
        contributionsCollection {
          totalCommitContributions
          totalIssueContributions
          totalPullRequestContributions
          totalPullRequestReviewContributions
          commitContributionsByRepository(maxRepositories: 100) {
            repository {
              nameWithOwner
              owner {
                login
                avatarUrl
                ... on Organization {
                  name
                }
              }
              isPrivate
              isFork
            }
            contributions {
              totalCount
            }
          }
          issueContributionsByRepository(maxRepositories: 100) {
            repository {
              nameWithOwner
              owner {
                login
                avatarUrl
                ... on Organization {
                  name
                }
              }
              isPrivate
            }
          }
          pullRequestContributionsByRepository(maxRepositories: 100) {
            repository {
              nameWithOwner
              owner {
                login
                avatarUrl
                ... on Organization {
                  name
                }
              }
              isPrivate
            }
          }
        }
      }
    }
    """ % USERNAME
    return graphql(query)


def extract_orgs(data: dict) -> list[dict]:
    """Extract unique external orgs the user has contributed to."""
    seen = set()
    orgs = []
    collection = data["data"]["user"]["contributionsCollection"]

    for key in [
        "commitContributionsByRepository",
        "issueContributionsByRepository",
        "pullRequestContributionsByRepository",
    ]:
        for entry in collection.get(key, []):
            repo = entry["repository"]
            if repo.get("isPrivate"):
                continue
            owner = repo["owner"]
            login = owner["login"]
            if login == USERNAME or login in seen:
                continue
            seen.add(login)
            orgs.append(
                {
                    "login": login,
                    "name": owner.get("name") or login,
                    "avatar": owner["avatarUrl"],
                }
            )

    orgs.sort(key=lambda o: o["login"].lower())
    return orgs


def extract_contrib_repos(data: dict) -> list[str]:
    """Extract unique external repos contributed to (not owned by user)."""
    seen = set()
    repos = []
    collection = data["data"]["user"]["contributionsCollection"]

    for key in [
        "commitContributionsByRepository",
        "issueContributionsByRepository",
        "pullRequestContributionsByRepository",
    ]:
        for entry in collection.get(key, []):
            repo = entry["repository"]
            if repo.get("isPrivate"):
                continue
            name = repo["nameWithOwner"]
            owner = repo["owner"]["login"]
            if owner == USERNAME or name in seen:
                continue
            seen.add(name)
            repos.append(name)

    repos.sort(key=str.lower)
    return repos


def build_markdown(orgs: list[dict], repos: list[str], data: dict) -> str:
    collection = data["data"]["user"]["contributionsCollection"]
    commits = collection["totalCommitContributions"]
    issues = collection["totalIssueContributions"]
    prs = collection["totalPullRequestContributions"]
    reviews = collection["totalPullRequestReviewContributions"]
    total = commits + issues + prs + reviews or 1

    lines = []

    # Org badges
    if orgs:
        lines.append("#### Organizations I've contributed to\n")
        lines.append("<p>")
        for org in orgs:
            lines.append(
                f'  <a href="https://github.com/{org["login"]}">'
                f'<img src="{org["avatar"]}&s=48" width="48" height="48" '
                f'alt="@{org["login"]}" title="@{org["login"]}" '
                f'style="border-radius:50%" />'
                f"</a>"
            )
        lines.append("</p>\n")

    # Contribution breakdown
    lines.append("#### Contribution breakdown (last year)\n")
    lines.append(f"**{commits}** commits · **{issues}** issues · **{prs}** pull requests · **{reviews}** code reviews\n")

    # Repos contributed to
    if repos:
        lines.append(
            "<details>\n<summary>Repositories contributed to outside my own</summary>\n"
        )
        lines.append("")
        for repo in repos:
            lines.append(f"- [{repo}](https://github.com/{repo})")
        lines.append("")
        lines.append("</details>")

    return "\n".join(lines)


def update_readme(section_md: str) -> None:
    with open(README_PATH, "r") as f:
        content = f.read()

    start_marker = "<!-- CONTRIBUTIONS:START -->"
    end_marker = "<!-- CONTRIBUTIONS:END -->"

    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        re.DOTALL,
    )

    replacement = f"{start_marker}\n{section_md}\n{end_marker}"

    if pattern.search(content):
        new_content = pattern.sub(replacement, content)
    else:
        new_content = content.rstrip() + f"\n\n{replacement}\n"

    with open(README_PATH, "w") as f:
        f.write(new_content)


def main():
    print("Fetching contribution data...")
    data = fetch_contributions()

    if "errors" in data:
        print(f"GraphQL errors: {data['errors']}")
        raise SystemExit(1)

    orgs = extract_orgs(data)
    repos = extract_contrib_repos(data)

    print(f"Found {len(orgs)} orgs, {len(repos)} external repos")

    section_md = build_markdown(orgs, repos, data)
    update_readme(section_md)
    print("README updated.")


if __name__ == "__main__":
    main()
