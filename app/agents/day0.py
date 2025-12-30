"""
Fixed Day 0 content for all projects.
Day 0 is always the same: GitHub setup and project initialization.
"""

from app.agents.state import ConceptData

DAY_0_THEME = {
    "day_number": 0,
    "theme": "Project Setup & GitHub Connection",
    "description": "Set up your development environment and connect your GitHub account to start building."
}

DAY_0_CONTENT: list[ConceptData] = [
    {
        "order_index": 1,
        "title": "GitHub Profile Setup",
        "description": "Connect your GitHub account and prepare your development workspace",
        "subconcepts": [
            {
                "order_index": 1,
                "title": "Why GitHub Matters",
                "content": """# Why GitHub Matters

GitHub is the world's largest platform for hosting and collaborating on code. It's where developers build software together and showcase their work.

**Why You Need GitHub:**
- **Version Control**: Track every change to your code
- **Collaboration**: Work with other developers
- **Portfolio**: Show employers your projects
- **Industry Standard**: Used by millions of developers

**Key Insight:**
Your GitHub profile is your developer resume. Recruiters and hiring managers check GitHub profiles to see real code you've written.

**What Makes a Strong Profile:**
- Active contributions (green squares!)
- Well-documented projects
- Clear README files
- Consistent commit history

Think of GitHub as LinkedIn for developers - but instead of listing skills, you prove them with code.
"""
            },
            {
                "order_index": 2,
                "title": "Setting Up Your Profile",
                "content": """# Setting Up Your Profile

A professional GitHub profile helps you stand out. Let's optimize yours.

**Essential Profile Elements:**

1. **Profile Photo**: Use a clear, professional photo
2. **Bio**: Describe yourself in 1-2 sentences
   - Example: "Full-stack developer learning AI/ML. Building projects in Python and React."
3. **Location**: Add your city/region
4. **Links**: Add your portfolio, LinkedIn, or Twitter

**Pinned Repositories:**
Pin your best 6 projects to the top of your profile. Choose projects that:
- Are complete and working
- Have good README files
- Show different skills
- Demonstrate your growth

**Profile README (Optional but Impressive):**
Create a special repository named exactly as your username to add a homepage to your profile.

**Example**: If your username is `johndoe`, create a repo called `johndoe` with a README.md - this appears on your profile page!

**Pro Tip**: Keep your profile updated. Add new projects as you build them.
"""
            },
            {
                "order_index": 3,
                "title": "Understanding Repositories",
                "content": """# Understanding Repositories

A repository (or "repo") is a project folder that contains all your code, files, and version history.

**What's Inside a Repository:**
- **Code files**: Your actual program files
- **README.md**: Project documentation
- **Commit history**: Every change ever made
- **.gitignore**: Files to exclude from version control
- **Branches**: Different versions of your code

**Repository Types:**

**Public Repositories:**
- Visible to everyone
- Free on GitHub
- Great for learning projects and portfolios
- Open for collaboration

**Private Repositories:**
- Only you (and invited collaborators) can see
- Good for work projects or unfinished code
- Still free on GitHub

**Best Practices:**
- Use clear, descriptive names (e.g., `todo-app` not `project1`)
- Always include a README file
- Add a license if you want others to use your code
- Write meaningful commit messages

**For This Learning Project:**
You'll create a public repository so you can showcase your progress and learning journey.
"""
            }
        ],
        "tasks": [
            {
                "order_index": 1,
                "title": "Verify Your GitHub Profile",
                "description": "Paste your GitHub profile URL (example: https://github.com/yourusername) so we can verify your account and track your learning progress. Make sure your profile is set up with at least a username and photo.",
                "task_type": "github_profile"
            },
            {
                "order_index": 2,
                "title": "Create Your Project Repository",
                "description": "Create a new public repository on GitHub for this learning project. Name it something descriptive related to what you're building (e.g., 'learning-python-basics' or 'my-first-webapp'). Initialize it with a README file. Copy and paste the repository URL when done.",
                "task_type": "create_repo"
            },
            {
                "order_index": 3,
                "title": "Make Your First Commit",
                "description": "Initialize your local repository, connect it to GitHub, and make your first commit. This verifies your GitHub connection is working. You can either: (1) Edit the README directly on GitHub and commit, or (2) Clone the repo locally, make a change, and push. Paste your commit URL to verify (example: https://github.com/username/repo/commit/abc123).",
                "task_type": "verify_commit"
            }
        ]
    }
]


def get_day_0_content() -> tuple[dict, list[ConceptData]]:
    """
    Returns Day 0 theme and content.
    
    Returns:
        tuple: (day_0_theme, day_0_concepts)
    """
    return DAY_0_THEME, DAY_0_CONTENT