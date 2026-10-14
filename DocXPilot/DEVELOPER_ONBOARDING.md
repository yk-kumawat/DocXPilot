# DocXPilot Developer Onboarding Guide

Welcome to the DocXPilot team! We're thrilled to have you on board. This guide is designed to get you up and running with the DocXPilot project quickly and efficiently. Our goal is to make your onboarding experience as smooth as possible so you can start contributing and making an impact right away.

DocXPilot is an innovative project designed to analyze existing project documentation, code, and activity to generate insightful reports and improve overall project understanding through AI-powered capabilities.

Let's get started!

---

## 🚀 Quick Start: Get DocXPilot Running in Under 10 Minutes

Follow these steps to set up your development environment and run DocXPilot for the first time.

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/yk-kumawat/DocXPilot.git
    cd DocXPilot
    ```

2.  **Create and Activate a Virtual Environment:**
    It's best practice to use a virtual environment to manage project dependencies.
    ```bash
    python -m venv .venv
    # On macOS/Linux:
    source .venv/bin/activate
    # On Windows:
    .venv\Scripts\activate
    ```

3.  **Install Dependencies:**
    DocXPilot uses `pip` for dependency management.
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set Up Environment Variables:**
    DocXPilot requires a `GEMINI_API_KEY` to interact with the Google Gemini AI models.
    *   Obtain your API key from [Google AI Studio](https://aistudio.google.com/app/apikey).
    *   Create or open the `.env` file in the root of the project directory.
    *   Add your API key:
        ```
        GEMINI_API_KEY="YOUR_GEMINI_API_KEY_HERE"
        ```

5.  **Run DocXPilot:**
    Now you can run the main application.
    ```bash
    python src/main.py
    ```
    You should see the command-line interface (CLI) prompt appear, ready for your commands!

---

## 🗺️ Repository Tour: Understanding the Project Layout

The DocXPilot project is structured to logically separate concerns, making it easier to navigate and contribute. Here's a breakdown of the key directories and files:

*   **`DocXPilot/`**:
    *   `PROJECT_REPORT.md`: This file likely contains the main generated project report or serves as a template/example for it.
*   **`src/`**: This directory contains all the core application source code.
    *   **`aggregator/`**: Responsible for collecting and consolidating information from various sources into a cohesive knowledge base.
        *   `knowledge_base.py`: Manages the structured data collected about the project.
    *   **`ai/`**: Houses components related to Artificial Intelligence interactions, specifically with Google Gemini.
        *   `doc_generator.py`: Logic for generating documentation or reports using AI.
        *   `gemini_client.py`: The client for interacting with the Google Gemini API.
        *   `prompts.py`: Defines the various prompts used to guide the AI's responses and generation tasks.
    *   **`analyzers/`**: A collection of modules designed to analyze different aspects of a project.
        *   `activity_analyzer.py`, `activity_dsp.py`, `activity_signal.py`: Analyze project activity patterns (e.g., commit frequency, contributor activity).
        *   `code_analyzer.py`: Inspects source code for insights (e.g., complexity, structure).
        *   `config_analyzer.py`: Parses and understands project configuration files.
        *   `dependency_analyzer.py`: Identifies and maps project dependencies.
        *   `directory_analyzer.py`: Scans and understands the project's directory structure.
        *   `docs_reader.py`: Reads and processes existing documentation.
        *   `git_analyzer.py`: Extracts information from the Git repository (history, branches, contributors).
        *   `models.py`: Data models used by the analyzers to represent project entities.
        *   `project.py`: Likely aggregates results from various analyzers to form a holistic project view.
    *   **`cli/`**: Contains the command-line interface logic.
        *   `commands.py`: Defines the available CLI commands and their arguments using `typer`.
        *   `ui.py`: Handles user interface elements and rich output for the CLI.
    *   **`ml/`**: Machine Learning components of the project.
        *   `weights/`: Directory for storing model weights or related data.
        *   `collect_data.py`: Scripts for gathering data for ML model training.
        *   `infer.py`: Logic for running inference with trained ML models.
        *   `model.py`: Defines the ML model architecture.
        *   `synthetic.py`: Likely for generating synthetic data for training/testing.
        *   `train.py`: Script for training ML models.
    *   **`output/`**: Modules responsible for writing processed data or generated reports to various output formats.
        *   `writer.py`: Handles the actual writing of output.
    *   `main.py`: The primary entry point for the DocXPilot application.
*   **`tests/`**: Contains unit and integration tests for the project.
    *   `test_activity.py`: Example test file.
*   **`.env`**: Stores environment variables, particularly sensitive API keys.
*   **`pyproject.toml`**: Project configuration file, potentially used for `poetry` or `flit` for project metadata and dependencies.
*   **`requirements.txt`**: Lists all Python package dependencies required by the project.

---

## 🛠️ Development Environment Setup

To ensure a consistent and productive development experience, we recommend the following setup:

*   **Python Version**: DocXPilot is developed with Python 3.8+. Ensure you have a compatible version installed.
*   **Virtual Environments**: Always work within a virtual environment (`.venv` as shown in Quick Start) to isolate project dependencies.
*   **Integrated Development Environment (IDE)**:
    *   **VS Code** is a popular choice. Install the official [Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python).
*   **Linters and Formatters**:
    *   **Black**: We use `black` for uncompromising code formatting. It's listed in `requirements.txt`.
        *   **Installation**: `pip install black` (if not already installed via `requirements.txt`).
        *   **Usage**: Run `black .` from the project root to format all Python files.
        *   **VS Code Integration**: Configure your VS Code Python extension to use `black` as the default formatter. You might need to add `"python.formatting.provider": "black"` to your `settings.json`.
    *   **Flake8/Ruff** (Recommended): While `black` handles formatting, a linter like `flake8` or `ruff` can catch style errors and potential bugs.
        *   **Installation**: `pip install flake8` or `pip install ruff`.
        *   **VS Code Integration**: Install the respective extensions and configure them.

---

## 📜 Code Conventions & Style Guide

Consistency is key for maintainable code. Please adhere to the following guidelines:

*   **PEP 8**: Follow the official Python style guide (PEP 8) for readability and consistency.
*   **Black Formatting**: All code must be formatted using `black`. Run `black .` before committing your changes. This automates most style concerns.
*   **Docstrings**:
    *   Provide clear and concise docstrings for all modules, classes, and functions.
    *   Use triple double-quotes (`"""Docstring goes here."""`).
    *   Briefly explain what the code does, its arguments, and what it returns (if applicable).
*   **Type Hints**: Use [type hints](https://docs.python.org/3/library/typing.html) for function arguments and return values to improve code clarity and enable static analysis.
    ```python
    def calculate_sum(a: int, b: int) -> int:
        """Calculates the sum of two integers."""
        return a + b
    ```
*   **Naming Conventions**:
    *   Variables and functions: `snake_case` (e.g., `my_variable`, `calculate_score`).
    *   Classes: `CamelCase` (e.g., `MyClass`, `ActivityAnalyzer`).
    *   Constants: `UPPER_SNAKE_CASE` (e.g., `MAX_RETRIES`).

---

## 🔑 Key Files & Entry Points

Understanding where the core logic resides is crucial:

*   **`src/main.py`**: This is the application's primary entry point. When you run `python src/main.py`, this script initializes the CLI and dispatches commands.
*   **`src/cli/commands.py`**: Defines all the top-level commands and subcommands available through the CLI. This is where you'll add new user-facing functionality.
*   **`src/ai/gemini_client.py`**: The central hub for all interactions with the Google Gemini API. If you need to make AI calls, this is where you'll find or add the necessary methods.
*   **`src/analyzers/`**: The heart of DocXPilot's data collection and analysis. Each file here focuses on a specific aspect of project analysis (e.g., `git_analyzer.py` for Git data, `code_analyzer.py` for code parsing).
*   **`src/ml/`**: If you're working on improving or extending the machine learning capabilities, this directory contains the training (`train.py`), inference (`infer.py`), and model definition (`model.py`) scripts.

---

## 🤝 Making Your First Contribution: A Step-by-Step Guide

We encourage contributions! Here’s how to make your first one:

1.  **Find a Task**: Look for issues on the GitHub repository or discuss with the team if you have an idea for an enhancement or bug fix.
2.  **Create a New Branch**: Always work on a new branch, named descriptively (e.g., `feature/add-new-analyzer`, `bugfix/fix-cli-error`).
    ```bash
    git checkout main
    git pull origin main
    git checkout -b feature/your-feature-name
    ```
3.  **Implement Your Changes**: Write your code, focusing on clarity, modularity, and adherence to the style guide.
4.  **Add/Update Tests**: If you're adding new functionality or fixing a bug, ensure there are corresponding tests (or update existing ones) in the `tests/` directory.
5.  **Run Tests**: Verify your changes haven't introduced regressions.
    ```bash
    pytest
    ```
6.  **Format Your Code**: Ensure your code is formatted correctly with `black`.
    ```bash
    black .
    ```
7.  **Commit Your Changes**: Write clear and concise commit messages.
    ```bash
    git add .
    git commit -m "feat: Add new feature for X"
    ```
8.  **Push Your Branch**:
    ```bash
    git push origin feature/your-feature-name
    ```
9.  **Open a Pull Request (PR)**:
    *   Go to the [DocXPilot GitHub repository](https://github.com/yk-kumawat/DocXPilot.git).
    *   You should see a prompt to open a PR from your newly pushed branch.
    *   Provide a clear title and description for your PR, explaining what it does and why.
    *   Request a review from the team.

---

## ✅ Running Tests

Tests are vital for maintaining code quality and preventing regressions.

*   **Prerequisites**: Ensure `pytest` is installed (`pip install pytest`). It's included in `requirements.txt`.
*   **Run All Tests**: From the project root directory:
    ```bash
    pytest
    ```
*   **Run Specific Test File**:
    ```bash
    pytest tests/test_activity.py
    ```
*   **Run Specific Test Function**:
    ```bash
    pytest tests/test_activity.py::test_some_function
    ```

---

## 🌳 Git Workflow

We follow a feature-branch workflow for DocXPilot development:

1.  **`main` Branch**: This branch represents the latest stable and deployable version of the project. Direct commits to `main` are generally discouraged.
2.  **Feature Branches**: All new development (features, bug fixes, refactors) should be done on dedicated feature branches created from `main`.
    *   Branch names should be descriptive (e.g., `feature/ai-enhancements`, `bugfix/cli-parser-bug`).
3.  **Pull Requests (PRs)**: Once your work on a feature branch is complete and tested, open a Pull Request to merge your branch into `main`.
    *   PRs are reviewed by other team members to ensure code quality, correctness, and adherence to project standards.
    *   Address any feedback or requested changes.
4.  **Squash and Merge**: Before merging, your commits might be squashed into a single, clean commit to keep the `main` branch history tidy.

---

## 🙋 Who to Ask for Help

Don't hesitate to reach out if you have questions, encounter issues, or need guidance.

*   **Primary Contact**:
    *   **Yogesh kumawat** (The project's primary contributor, found in Git history)
*   **GitHub Issues**: For bugs, feature requests, or general discussions, open an issue on the [DocXPilot GitHub repository](https://github.com/yk-kumawat/DocXPilot.git/issues).
*   **Pull Request Comments**: Use PR comments for specific code-related questions or feedback during reviews.

---

## 📚 Glossary of Project-Specific Terms

*   **DocXPilot**: The name of our project, focusing on AI-powered documentation and project analysis.
*   **Aggregator**: Refers to the `src/aggregator` module, responsible for collecting and consolidating diverse project information.
*   **Analyzers**: The modules within `src/analyzers` that perform specific analysis tasks (e.g., `GitAnalyzer`, `CodeAnalyzer`).
*   **Knowledge Base**: The structured representation of project data built by the aggregator, used by AI and other components.
*   **Gemini Client**: The `src/ai/gemini_client.py` module, which handles all communication with the Google Gemini AI models.
*   **CLI**: Command-Line Interface, the primary way users interact with DocXPilot (`src/cli/`).
*   **ML**: Machine Learning, referring to the components in `src/ml/` for data collection, model training, and inference.

---

We're excited to see your contributions to DocXPilot! Happy coding!