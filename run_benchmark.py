from __future__ import annotations
import json
from pathlib import Path
import typer
from rich import print
from rich.progress import track
from src.reflexion_lab.agents import ReActAgent, ReflexionAgent
from src.reflexion_lab.reporting import build_report, save_report
from src.reflexion_lab.utils import load_dataset, save_jsonl
from src.reflexion_lab.llm_runtime import LLMRuntime
from prepare_data import download_hotpot_qa

app = typer.Typer(add_completion=False)


@app.command()
def main(
    dataset: str = "data/hotpot_qa.json",
    out_dir: str = "outputs/reflexion_run",
    reflexion_attempts: int = 3,
    use_mock: bool = False,
    llm_model: str = "gpt-4-turbo",
    use_ollama: bool = False,
    num_samples: int = 100,
    limit_examples: int = 0,
) -> None:
    """
    Run Reflexion Agent benchmark
    
    Args:
        dataset: Path to dataset JSON file
        out_dir: Output directory for results
        reflexion_attempts: Max attempts for Reflexion agent
        use_mock: Use mock data instead of real LLM
        llm_model: LLM model to use
        use_ollama: Use Ollama local server instead of OpenAI
        num_samples: Number of samples to generate/use from dataset
        limit_examples: Limit number of examples to process (0 = all)
    """
    # Prepare dataset
    dataset_path = Path(dataset)
    if not dataset_path.exists():
        print(f"[yellow]Dataset not found at {dataset}, generating...[/yellow]")
        download_hotpot_qa(str(dataset_path), num_samples=num_samples)
    
    # Load dataset
    print(f"[cyan]Loading dataset from {dataset}...[/cyan]")
    examples = load_dataset(dataset)
    
    if limit_examples > 0:
        examples = examples[:limit_examples]
    
    print(f"[cyan]Loaded {len(examples)} examples[/cyan]")
    
    # Initialize LLM if not using mock
    if not use_mock:
        llm_runtime = LLMRuntime(
            model=llm_model,
            use_ollama=use_ollama,
        )
        print(f"[cyan]Using LLM: {llm_model} (Ollama: {use_ollama})[/cyan]")
    else:
        llm_runtime = None
        print(f"[cyan]Using MOCK runtime[/cyan]")
    
    # Run agents
    print(f"[cyan]Running ReAct Agent...[/cyan]")
    react = ReActAgent(use_mock=use_mock, llm_runtime=llm_runtime)
    react_records = []
    for example in track(examples, description="ReAct"):
        react_records.append(react.run(example))
    
    print(f"[cyan]Running Reflexion Agent (max {reflexion_attempts} attempts)...[/cyan]")
    reflexion = ReflexionAgent(max_attempts=reflexion_attempts, use_mock=use_mock, llm_runtime=llm_runtime)
    reflexion_records = []
    for example in track(examples, description="Reflexion"):
        reflexion_records.append(reflexion.run(example))
    
    # Save results
    print(f"[cyan]Generating report...[/cyan]")
    all_records = react_records + reflexion_records
    out_path = Path(out_dir)
    save_jsonl(out_path / "react_runs.jsonl", react_records)
    save_jsonl(out_path / "reflexion_runs.jsonl", reflexion_records)
    
    mode = "mock" if use_mock else f"real ({llm_model})"
    report = build_report(all_records, dataset_name=Path(dataset).name, mode=mode)
    json_path, md_path = save_report(report, out_path)
    
    print(f"[green]Saved[/green] {json_path}")
    print(f"[green]Saved[/green] {md_path}")
    print(json.dumps(report.summary, indent=2))


if __name__ == "__main__":
    app()

