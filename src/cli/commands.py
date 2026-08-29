import typer

from analyzers.project import analyze
from cli.ui import title, success

app = typer.Typer()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """DocXPilot - AI-powered documentation generator."""

    if ctx.invoked_subcommand is None:
        title("DocXPilot")

        print("Welcome to DocXPilot!")
        print()
        print("Use 'docxpilot --help' to see available commands.")


@app.command()
def project(path: str):

    title("Project Analyzer")

    result = analyze(path)

    print(result)

    success("Analysis Completed")