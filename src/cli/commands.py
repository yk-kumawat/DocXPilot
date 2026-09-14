import typer

from analyzers.project import analyze
from cli.ui import title, success, main_menu

app = typer.Typer()

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """DocXPilot - AI-enhanced documentation generator."""

    if ctx.invoked_subcommand is None:

        title("DocXPilot - AI-enhanced documentation generator.")

        print("Welcome to DocXPilot!")
        print()
        print("Use 'docxpilot --help' to see available commands.")

        choice = main_menu()

        if choice == "Generate Documentation":
            print("Generate Documentation selected")

        elif choice == "Select Documents to Generate":
            print("Select Documents to Generate selected")

        elif choice == "Set Document Formats":
            print("Set Document Formats selected")

        elif choice == "Exit":
            print("Goodbye!")


@app.command()
def project(path: str):
    """Analyze a project."""

    title("Project Analyzer")

    result = analyze(path)

    print(result)

    success("Analysis Completed")