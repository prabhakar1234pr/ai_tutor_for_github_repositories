"""
Fixed Day 0 content for all projects.
Day 0 is always the same: GitHub setup and project initialization.
Content is comprehensive documentation for the full-page docs experience.
"""

from app.agents.state import ConceptData

DAY_0_THEME = {
    "day_number": 0,
    "theme": "Project Setup & GitHub Connection",
    "description": "Set up your development environment and connect your GitHub account to start building.",
}

DAY_0_CONTENT: list[ConceptData] = [
    {
        "order_index": 1,
        "title": "GitHub Profile Setup",
        "description": "Connect your GitHub account and prepare your development workspace",
        "estimated_minutes": 25,
        "content": """# GitHub Profile Setup

## Introduction

Welcome to your learning journey! Before we dive into coding, we need to set up the foundation that every professional developer uses: **GitHub**.

GitHub is more than just a place to store code—it's the central hub of modern software development. Whether you're building a personal project, contributing to open source, or working at a tech company, you'll be using GitHub daily.

> 💡 **Why This Matters**: Your GitHub profile is your developer portfolio. Recruiters and hiring managers check GitHub profiles to see real code you've written. A well-maintained profile can open doors to job opportunities.

In this section, you'll learn what GitHub is, why it's essential, and how to set up your profile for success.

---

## Core Concepts

### What is GitHub?

**GitHub** is a web-based platform for version control and collaboration. It lets you and others work together on projects from anywhere in the world.

At its core, GitHub uses **Git**, a distributed version control system that tracks changes to files. Think of it like a detailed history book for your code—you can see every change ever made, who made it, and when.

**Key Features of GitHub:**
- **Repositories**: Projects that contain all your files and revision history
- **Commits**: Snapshots of your project at specific points in time
- **Branches**: Parallel versions of your code for developing features
- **Pull Requests**: Proposed changes that can be reviewed before merging
- **Issues**: Bug tracking and feature requests
- **Actions**: Automated workflows for testing and deployment

### Why Developers Use GitHub

GitHub isn't just popular—it's the industry standard. Here's why:

1. **Version Control**: Never lose work. Every change is saved and can be reverted.
2. **Collaboration**: Work with teams of any size, anywhere in the world.
3. **Portfolio**: Showcase your projects to potential employers.
4. **Community**: Access millions of open-source projects to learn from.
5. **Integration**: Works with almost every development tool.

> 📊 **Fun Fact**: GitHub hosts over 100 million repositories and has more than 83 million developers as of 2023.

---

## How It Works

### The GitHub Workflow

Understanding the basic GitHub workflow is essential:

```
1. Create Repository → 2. Clone to Local → 3. Make Changes → 4. Commit → 5. Push → 6. Repeat
```

**Step-by-step breakdown:**

1. **Create a Repository**: Start a new project on GitHub
2. **Clone**: Download the repository to your computer
3. **Make Changes**: Edit files, add features, fix bugs
4. **Stage & Commit**: Save your changes with a descriptive message
5. **Push**: Upload your commits back to GitHub
6. **Pull**: Download changes made by others (for team projects)

### Understanding Repositories

A **repository** (or "repo") is like a project folder that contains:
- All your code files
- Documentation (README, LICENSE)
- Configuration files
- Complete history of every change

**Repository Types:**

| Type | Visibility | Best For |
|------|------------|----------|
| Public | Everyone | Open source, portfolios |
| Private | Only you + collaborators | Work projects, unfinished code |

### Understanding Licenses

A **license** is a legal document that tells others what they can and cannot do with your code. Without a license, your code is technically "all rights reserved"—meaning no one can legally use, modify, or distribute it.

**Why Licenses Matter:**
- They protect your work legally
- They clarify how others can use your code
- They encourage (or restrict) collaboration
- They're required for professional and open-source projects

**Common License Types:**

| License | Permissions | Restrictions | Best For |
|---------|-------------|--------------|----------|
| **MIT** | Use, modify, distribute, commercial use | Must include license text | Simple projects, maximum freedom |
| **Apache 2.0** | Use, modify, distribute, patent rights | Must include license + state changes | Projects needing patent protection |
| **GPL v3** | Use, modify, distribute | Derivatives must also be GPL | Ensuring code stays open source |
| **BSD 3-Clause** | Use, modify, distribute | Cannot use author's name for endorsement | Academic and research projects |
| **Unlicense** | Anything | None | Public domain dedication |

**How to Choose a License:**

1. **Want maximum freedom?** → Use **MIT** or **BSD**
   - Anyone can do almost anything with your code
   - Only requirement: include the original license

2. **Want patent protection?** → Use **Apache 2.0**
   - Protects against patent claims
   - Good for larger projects

3. **Want derivatives to stay open source?** → Use **GPL**
   - "Copyleft" license
   - Any project using your code must also be GPL

4. **Not sure?** → **MIT is the safest default**
   - Most permissive and widely understood
   - Used by React, jQuery, and many major projects

> ⚠️ **Important**: Once you choose a license, it applies to all future users. Changing licenses later can be complicated if others have already used your code.

**Adding a License to Your Repository:**

When creating a new repository on GitHub:
1. Check "Add a license" during creation
2. Select your preferred license from the dropdown
3. GitHub automatically creates a `LICENSE` file

For existing repositories:
1. Create a new file called `LICENSE` (no extension)
2. Copy the full license text from [choosealicense.com](https://choosealicense.com)
3. Commit the file to your repository

---

## Setting Up Your Profile

### Essential Profile Elements

A professional GitHub profile should include:

1. **Profile Photo**: Use a clear, professional photo (or a distinctive avatar)
2. **Name**: Your real name helps people find and remember you
3. **Bio**: A brief description (160 characters max)
4. **Location**: Your city or timezone
5. **Links**: Portfolio, LinkedIn, or personal website

**Example Bio:**
```
Full-stack developer passionate about React and Python. Building tools that make developers' lives easier. Open to opportunities!
```

### Pinned Repositories

You can pin up to 6 repositories to the top of your profile. Choose projects that:
- ✅ Are complete and functional
- ✅ Have clear README files
- ✅ Demonstrate your best skills
- ✅ Show variety in your abilities

> 💡 **Pro Tip**: Pin a mix of project types—maybe a web app, a CLI tool, and a contribution to an open-source project.

### Profile README (Advanced)

You can create a special repository with the same name as your username to add a README that appears on your profile page.

**Example**: If your username is `johndoe`, create a repo called `johndoe` with a `README.md`. This markdown file becomes your profile homepage!

---

## Common Patterns

### Good Repository Practices

Every repository should have:

1. **README.md**: Explains what the project does and how to use it
2. **.gitignore**: Lists files Git should ignore (like `node_modules/`)
3. **LICENSE**: Tells others how they can use your code
4. **Clear commit messages**: Describe what each change does

**Good commit message examples:**
```
✅ "Add user authentication with JWT tokens"
✅ "Fix navbar not displaying on mobile devices"
✅ "Update README with installation instructions"

❌ "fix stuff"
❌ "asdfasdf"
❌ "changes"
```

### Contribution Graph

Your GitHub profile shows a contribution graph—a calendar of green squares representing your activity. Each square represents a day, and the color intensity shows how many contributions you made.

**What counts as a contribution:**
- Commits to a repository's default branch
- Opening issues or pull requests
- Reviewing pull requests
- Creating repositories

> 🎯 **Goal**: Consistent activity (even small commits) looks better than sporadic bursts.

---

## Common Mistakes

### Mistake 1: Empty or Unclear README

A repository without a README is like a book without a cover. Always include:
- What the project does
- How to install/run it
- How to use it
- (Optional) Screenshots or demos

### Mistake 2: Committing Sensitive Data

**Never commit:**
- Passwords or API keys
- `.env` files with secrets
- Private configuration files

Use a `.gitignore` file and environment variables instead.

### Mistake 3: Inconsistent Activity

Having months of inactivity followed by sudden bursts looks unprofessional. Try to:
- Work on projects regularly
- Make small, frequent commits
- Keep learning and building

---

## Personal Access Tokens (PATs)

### What is a Personal Access Token?

A **Personal Access Token (PAT)** is a secure way to authenticate with GitHub without using your password. Think of it as a special key that grants specific permissions to applications or services.

**Why We Use PATs:**
- More secure than passwords (can be revoked individually)
- Scoped to specific repositories and permissions
- Fine-grained control over what access is granted
- Required for GitGuide to sync your code and verify your progress

### Understanding Fine-Grained PATs

GitHub offers two types of PATs:
1. **Classic PATs**: Broad access to all repositories (not what we need)
2. **Fine-Grained PATs**: Scoped to specific repositories with granular permissions (what we use)

**Fine-Grained PAT Benefits:**
- ✅ Access only to your specific repository (not all repos)
- ✅ Granular permissions (read/write contents only)
- ✅ More secure and privacy-focused
- ✅ Can be revoked anytime without affecting other access

### How to Create a Fine-Grained PAT

**Step-by-Step Instructions:**

1. **Navigate to GitHub Settings**
   - Click your profile picture (top right)
   - Select "Settings"
   - Scroll down to "Developer settings" (left sidebar)
   - Click "Personal access tokens"
   - Click "Fine-grained tokens"
   - Click "Generate new token"

2. **Configure Token Settings**
   - **Token name**: Enter a descriptive name (e.g., "GitGuide Learning Project")
   - **Description**: Optional, but helpful (e.g., "For GitGuide learning platform")
   - **Expiration**: Choose expiration period (90 days recommended for learning projects)

3. **Set Repository Access**
   - Select **"Only select repositories"**
   - Search for and select the repository you created in Task 2
   - ⚠️ **Important**: Do NOT select "All repositories" - this gives access to everything

4. **Set Repository Permissions**
   - Expand **"Repository permissions"** section
   - Find **"Contents"** permission
   - Select **"Read and write"** (required for GitGuide to commit and push)
   - Leave other permissions as "No access" (we only need Contents access)

5. **Generate and Copy Token**
   - Click **"Generate token"** button
   - ⚠️ **Critical**: Copy the token immediately - GitHub only shows it once!
   - Store it securely - you'll paste it into GitGuide in the next task

**Security Best Practices:**
- Never share your PAT with anyone
- Don't commit PATs to your repository
- Revoke old tokens if you generate new ones
- Set reasonable expiration dates
- Use fine-grained tokens (not classic) for better security

### Why GitGuide Needs Your PAT

GitGuide uses your PAT to:
- **Clone your repository** into the workspace container
- **Pull latest changes** before you start working
- **Commit your code** after task completion
- **Push changes** to GitHub to save your progress
- **Verify your work** by comparing code changes

**What GitGuide Does NOT Do:**
- Access your other repositories
- Modify your account settings
- Delete repositories
- Access your private information
- Make changes outside your learning repository

---

## Summary

You now understand:

- **GitHub** is the central hub for code collaboration and version control
- **Repositories** are project containers with full history tracking
- **Your profile** is your developer portfolio—keep it professional
- **Good practices** include clear READMEs, meaningful commits, and consistent activity

**Key Actions:**
- ✅ Set up your profile with photo, bio, and links
- ✅ Understand the commit → push workflow
- ✅ Know what makes a professional repository
- ✅ Avoid common mistakes like committing secrets

**Next Steps:** Complete the tasks below to verify your GitHub setup, create your repository, connect your account, and make your first commit!
""",
        "tasks": [
            {
                "order_index": 1,
                "title": "Verify Your GitHub Profile",
                "description": "Paste your GitHub profile URL (example: https://github.com/yourusername) to verify your account. Before submitting, make sure your profile has: 1) A profile photo or avatar, 2) Your name filled in, 3) A short bio describing yourself as a developer. We'll verify your profile is set up correctly.",
                "task_type": "github_profile",
                "estimated_minutes": 5,
                "difficulty": "easy",
            },
            {
                "order_index": 2,
                "title": "Create Your Project Repository",
                "description": "Create a new PUBLIC repository on GitHub for this learning project. Requirements: 1) Name it something descriptive (e.g., 'learning-python-api' or 'my-first-webapp'), 2) Check 'Add a README file' when creating, 3) Choose a license (MIT is a good default). After creating, paste the repository URL (example: https://github.com/username/repo-name).",
                "task_type": "create_repo",
                "estimated_minutes": 5,
                "difficulty": "easy",
            },
            {
                "order_index": 3,
                "title": "Make Your First Commit",
                "description": "Edit your repository's README.md file to personalize it. Add: 1) A project title, 2) A brief description of what you'll be learning, 3) Your name as the author. You can edit directly on GitHub (click the pencil icon) or clone locally and push. After committing, paste the commit URL (example: https://github.com/username/repo/commit/abc123).",
                "task_type": "verify_commit",
                "estimated_minutes": 10,
                "difficulty": "easy",
            },
            {
                "order_index": 4,
                "title": "Connect GitHub Account & Accept Terms",
                "description": "To enable code synchronization and accurate task verification, GitGuide needs access to your repository. We'll also verify your token can read the latest commit and that it matches the commit you provided in Task 3. Create a fine-grained Personal Access Token (PAT) scoped only to your repository. Step-by-step instructions: 1) Go to GitHub Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token, 2) Name your token (e.g., 'GitGuide Learning'), 3) Set expiration (90 days recommended), 4) Under 'Repository access', select 'Only select repositories' and choose the repository you created in Task 2, 5) Under 'Repository permissions', expand 'Contents' and select 'Read and write', 6) Click 'Generate token' and copy the token immediately (you won't see it again). Paste the token below and accept the terms to continue.",
                "task_type": "github_connect",
                "estimated_minutes": 10,
                "difficulty": "easy",
                "hints": [
                    "Make sure you select 'Only select repositories' and choose your specific repository, not 'All repositories'",
                    "The token must have 'Contents' read and write permissions",
                    "Copy the token immediately after generation - GitHub only shows it once",
                    "If you lose the token, you'll need to generate a new one",
                ],
            },
        ],
    }
]


def get_day_0_content() -> tuple[dict, list[ConceptData]]:
    """
    Returns Day 0 theme and content.

    Returns:
        tuple: (day_0_theme, day_0_concepts)
    """
    return DAY_0_THEME, DAY_0_CONTENT
