import os
import typer

from analyzers.project import analyze
from cli.ui import title, success, main_menu, select_documents_menu, confirm_generation

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
            output_dir = confirm_generation("DocXPilot")
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                print("Starting document generation...")
                success("Document generation started")

        elif choice == "Select Documents to Generate":
            selected_docs = select_documents_menu()
            if selected_docs:
                print(f"Selected documents: {', '.join(selected_docs)}")
            elif selected_docs is not None:
                print("No documents selected.")

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