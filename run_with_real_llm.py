#!/usr/bin/env python
"""
Run benchmark with Real OpenAI LLM using .env configuration
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import typer
from rich import print

# Load .env file
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"[cyan]✓ Loaded .env from {env_path}[/cyan]")

# Verify API key
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("[red]✗ OPENAI_API_KEY not found in .env[/red]")
    sys.exit(1)

print(f"[green]✓ OPENAI_API_KEY found[/green]")

# Import after loading .env
from src.reflexion_lab.agents import ReActAgent, ReflexionAgent
from src.reflexion_lab.reporting import build_report, save_report
from src.reflexion_lab.utils import load_dataset, save_jsonl
from src.reflexion_lab.llm_runtime import LLMRuntime
from prepare_data import download_hotpot_qa

app = typer.Typer(add_completion=False)


@app.command()
def main(
    dataset: str = "data/hotpot_qa.json",
    out_dir: str = "outputs/reflexion_run_real",
    reflexion_attempts: int = 3,
    llm_model: str = "gpt-4o-mini",  # Cheaper model for testing
    num_samples: int = 100,
    limit_examples: int = 20,  # Default to 20 for cost control
) -> None:
    """
    Run Reflexion Agent benchmark with Real OpenAI API
    
    Args:
        dataset: Path to dataset JSON file
        out_dir: Output directory for results
        reflexion_attempts: Max attempts for Reflexion agent
        llm_model: OpenAI model to use (gpt-4o-mini, gpt-4-turbo, etc.)
        num_samples: Number of samples to use from dataset
        limit_examples: Limit number of examples to process (0 = all loaded)
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
    
    # Initialize real LLM runtime
    print(f"[cyan]Initializing {llm_model} from OpenAI API...[/cyan]")
    llm_runtime = LLMRuntime(
        model=llm_model,
        api_key=api_key,
    )
    print(f"[green]✓ LLM Runtime initialized[/green]")
    
    # Run agents
    from rich.progress import track
    
    print(f"[cyan]Running ReAct Agent...[/cyan]")
    react = ReActAgent(use_mock=False, llm_runtime=llm_runtime)
    react_records = []
    for example in track(examples, description="ReAct"):
        try:
            react_records.append(react.run(example))
        except Exception as e:
            print(f"[red]Error processing {example.qid}: {e}[/red]")
    
    print(f"[cyan]Running Reflexion Agent (max {reflexion_attempts} attempts)...[/cyan]")
    reflexion = ReflexionAgent(max_attempts=reflexion_attempts, use_mock=False, llm_runtime=llm_runtime)
    reflexion_records = []
    for example in track(examples, description="Reflexion"):
        try:
            reflexion_records.append(reflexion.run(example))
        except Exception as e:
            print(f"[red]Error processing {example.qid}: {e}[/red]")
    
    # Save results
    print(f"[cyan]Generating report...[/cyan]")
    all_records = react_records + reflexion_records
    out_path = Path(out_dir)
    save_jsonl(out_path / "react_runs.jsonl", react_records)
    save_jsonl(out_path / "reflexion_runs.jsonl", reflexion_records)
    
    report = build_report(all_records, dataset_name=Path(dataset).name, mode=f"real ({llm_model})")
    json_path, md_path = save_report(report, out_path)
    
    print(f"[green]✓ Saved[/green] {json_path}")
    print(f"[green]✓ Saved[/green] {md_path}")
    
    # Print summary
    import json
    print("\n[cyan]Summary:[/cyan]")
    print(json.dumps(report.summary, indent=2))


if __name__ == "__main__":
    app()
