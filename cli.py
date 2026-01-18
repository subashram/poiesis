#!/usr/bin/env python3
"""
CLI for the Agent Workflow Engine.

Usage:
    python cli.py status              - Show workflow status
    python cli.py list                - List all tasks
    python cli.py validate            - Validate workflow
    python cli.py contracts "<desc>"  - Generate contracts
    python cli.py plan "<goal>"       - Decompose goal into tasks
    python cli.py run <task_id>       - Run a specific task
    python cli.py run-next            - Run the next available task
    python cli.py redteam <target>    - Run red team analysis
    python cli.py qa <target>         - Run QA verification
    python cli.py review              - Show tasks pending review
    python cli.py approve <task_id>   - Approve a reviewed task
    python cli.py reject <task_id>    - Reject a task
    python cli.py export-done         - Export approved artifacts for air-gapped transfer
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.engine import WorkflowEngine
from src.models import TaskStatus, TaskType, AgentType


def get_engine() -> WorkflowEngine:
    """Initialize and return the workflow engine."""
    engine = WorkflowEngine(Path(__file__).parent)
    print("Initializing workflow engine...")
    engine.initialize()
    return engine


def cmd_status(args):
    """Show workflow status."""
    engine = get_engine()
    status = engine.get_status()
    
    print("\n" + "="*50)
    print("WORKFLOW STATUS")
    print("="*50)
    print(f"Total tasks:       {status['total_tasks']}")
    print(f"  - Contracts:     {status['contract_tasks']}")
    print(f"  - Implementations: {status['implementation_tasks']}")
    print(f"Completed:         {status['completed']}")
    print(f"Pending:           {status['pending']}")
    print(f"In Review:         {status['in_review']}")
    print(f"In Loop:           {status['in_loop']}")
    
    # Context info
    if status['context_size'] > 0:
        size_kb = status['context_size'] / 1024
        mode = "🔍 Smart retrieval" if status['smart_retrieval'] else "📋 Full context"
        print(f"Design context:    {mode} ({size_kb:.1f} KB)")
    else:
        print(f"Design context:    ✗ None")
    
    print(f"QA Agent:          {'🧪 Available' if status['has_qa'] else '✗ Not configured'}")
    print(f"Red Team Agent:    {'🔴 Available' if status['has_redteam'] else '✗ Not configured'}")
    print(f"\nReady to run:      {', '.join(status['ready']) or 'None'}")
    print("="*50 + "\n")


def cmd_list(args):
    """List all tasks."""
    engine = get_engine()
    
    print("\n" + "="*90)
    print("TASKS")
    print("="*90)
    print(f"{'ID':<30} {'Type':<15} {'Status':<12} {'Loop':<6} {'Title'}")
    print("-"*90)
    
    for task_id, task in engine.state.tasks.items():
        status_icon = {
            TaskStatus.PENDING: "⏳",
            TaskStatus.RUNNING: "🔄",
            TaskStatus.REVIEW: "📋",
            TaskStatus.COMPLETED: "✅",
            TaskStatus.FAILED: "❌",
            TaskStatus.REJECTED: "🔙",
            TaskStatus.REWORK: "🔄",
        }.get(task.status, "?")
        
        type_icon = {
            TaskType.CONTRACT: "📜",
            TaskType.IMPLEMENTATION: "🔧",
            TaskType.TEST: "🧪",
            TaskType.DOCUMENTATION: "📄",
            TaskType.PLANNING: "📊",
        }.get(task.task_type, "?")
        
        if task.loop_config.enabled:
            loop_info = f"🔄{task.loop_state.iteration}/{task.loop_config.max_iterations}"
        else:
            loop_info = "  -  "
        
        print(f"{task_id:<30} {type_icon} {task.task_type.value:<12} {status_icon} {task.status.value:<10} {loop_info} {task.title}")
    
    print("="*90)
    print("📜=Contract | 🔧=Implementation | 🧪=Test | 🔄=Loop enabled (iteration/max)")
    print("="*90 + "\n")


def cmd_validate(args):
    """Validate workflow ordering and contracts."""
    engine = get_engine()
    
    print("\n" + "="*60)
    print("WORKFLOW VALIDATION")
    print("="*60)
    
    warnings = engine.validate_workflow()
    
    if not warnings:
        print("\n✅ Workflow is valid!\n")
    else:
        print(f"\n⚠️  Found {len(warnings)} issue(s):\n")
        for warning in warnings:
            print(f"  {warning}")
        print()
    
    print("="*60 + "\n")


def cmd_contracts(args):
    """Generate contracts for a feature."""
    engine = get_engine()
    
    try:
        result = engine.generate_contracts(
            feature=args.feature,
            output_file=args.output if args.output else None
        )
        
        print("\n" + "="*60)
        print("GENERATED CONTRACTS")
        print("="*60)
        print(result)
        print("="*60 + "\n")
        
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_redteam(args):
    """Run red team analysis on a task or file."""
    engine = get_engine()
    
    try:
        if args.target in engine.state.tasks:
            task = engine.state.tasks[args.target]
            artifact_file = engine.artifacts_path / f"{args.target}.md"
            if not artifact_file.exists():
                artifact_file = engine.done_path / f"{args.target}.md"
            
            if not artifact_file.exists():
                print(f"No artifact found for task: {args.target}")
                sys.exit(1)
            
            result = engine.redteam_artifact(str(artifact_file), output_file=args.output)
        else:
            result = engine.redteam_artifact(args.target, output_file=args.output)
        
        print("\n" + "="*60)
        print("🔴 RED TEAM REPORT")
        print("="*60)
        print(result)
        print("="*60 + "\n")
        
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_qa(args):
    """Run QA verification on a task or file."""
    engine = get_engine()
    
    try:
        contract = None
        criteria = None
        
        if args.target in engine.state.tasks:
            task = engine.state.tasks[args.target]
            contract = task.output_contract
            criteria = task.acceptance_criteria
            
            artifact_file = engine.artifacts_path / f"{args.target}.md"
            if not artifact_file.exists():
                artifact_file = engine.done_path / f"{args.target}.md"
            
            if not artifact_file.exists():
                print(f"No artifact found for task: {args.target}")
                sys.exit(1)
            
            result = engine.qa_artifact(
                str(artifact_file), 
                output_file=args.output,
                contract=contract,
                criteria=criteria
            )
        else:
            result = engine.qa_artifact(args.target, output_file=args.output)
        
        print("\n" + "="*60)
        print("🧪 QA REPORT")
        print("="*60)
        print(result)
        print("="*60 + "\n")
        
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_run(args):
    """Run a specific task."""
    engine = get_engine()
    
    if args.task_id:
        success = engine.run_task(args.task_id)
        sys.exit(0 if success else 1)
    else:
        print("Error: task_id required")
        sys.exit(1)


def cmd_run_next(args):
    """Run the next available task."""
    engine = get_engine()
    ready = engine.state.get_ready_tasks()
    
    if not ready:
        print("No tasks ready to run.")
        print("Check if there are tasks pending review: python cli.py review")
        sys.exit(0)
    
    contract_tasks = [t for t in ready if t.task_type == TaskType.CONTRACT]
    rework_tasks = [t for t in ready if t.status == TaskStatus.REWORK]
    
    if contract_tasks:
        task = contract_tasks[0]
        print(f"📜 Prioritizing contract task: {task.id}")
    elif rework_tasks:
        task = rework_tasks[0]
        print(f"🔄 Prioritizing rework task: {task.id}")
    else:
        task = ready[0]
    
    print(f"Running: {task.id}")
    success = engine.run_task(task.id)
    sys.exit(0 if success else 1)


def cmd_review(args):
    """Show tasks pending review."""
    engine = get_engine()
    items = engine.list_review_queue()
    
    if not items:
        print("\n✨ No tasks pending review!\n")
        return
    
    print("\n" + "="*80)
    print("TASKS PENDING REVIEW")
    print("="*80)
    
    contracts = [i for i in items if i['task_type'] == 'contract']
    others = [i for i in items if i['task_type'] != 'contract']
    
    if contracts:
        print("\n📜 CONTRACTS (review these first!):")
        for item in contracts:
            print(f"\n   {item['id']}: {item['title']}")
            print(f"   File: {item['file']}")
            print(f"   Approve: python cli.py approve {item['id']}")
    
    if others:
        print("\n🔧 OTHER TASKS:")
        for item in others:
            indicators = []
            if item.get('has_qa'):
                indicators.append("🧪 QA")
            if item.get('has_redteam'):
                indicators.append("🔴 RT")
            if item.get('loop_iterations', 0) > 0:
                indicators.append(f"🔄 {item['loop_iterations']} iter")
            
            indicator_str = f" [{', '.join(indicators)}]" if indicators else ""
            
            print(f"\n   {item['id']}{indicator_str}")
            print(f"   File: {item['file']}")
            print(f"   Approve: python cli.py approve {item['id']}")
    
    print("\n" + "="*80 + "\n")


def cmd_approve(args):
    """Approve a reviewed task."""
    engine = get_engine()
    success = engine.approve_task(args.task_id)
    sys.exit(0 if success else 1)


def cmd_reject(args):
    """Reject a task."""
    engine = get_engine()
    reason = args.reason or "No reason provided"
    success = engine.reject_task(args.task_id, reason)
    sys.exit(0 if success else 1)


def cmd_run_all(args):
    """Run all available tasks until none are ready."""
    engine = get_engine()
    
    while True:
        ready = engine.state.get_ready_tasks()
        if not ready:
            break
        
        contract_tasks = [t for t in ready if t.task_type == TaskType.CONTRACT]
        rework_tasks = [t for t in ready if t.status == TaskStatus.REWORK]
        
        if contract_tasks:
            task = contract_tasks[0]
        elif rework_tasks:
            task = rework_tasks[0]
        else:
            task = ready[0]
            
        print(f"\n{'='*60}")
        print(f"Running: {task.id} ({task.task_type.value})")
        if task.loop_config.enabled:
            print(f"Loop: Enabled (max {task.loop_config.max_iterations} iterations)")
        print(f"{'='*60}")
        
        success = engine.run_task(task.id)
        if not success:
            print(f"Task failed: {task.id}")
            break
        
        if task.requires_human_approval:
            print(f"\n⏸️  Paused - task requires human review")
            break
    
    cmd_status(args)


def cmd_plan(args):
    """Use planning agent to decompose a goal into tasks."""
    engine = get_engine()
    
    try:
        result = engine.plan_feature(
            goal=args.goal,
            output_file=args.output if args.output else None
        )
        
        print("\n" + "="*60)
        print("GENERATED TASK BREAKDOWN")
        print("="*60)
        print(result)
        print("="*60 + "\n")
        
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_show(args):
    """Show details of a specific task."""
    engine = get_engine()
    
    if args.task_id not in engine.state.tasks:
        print(f"Task not found: {args.task_id}")
        sys.exit(1)
    
    task = engine.state.tasks[args.task_id]
    
    print(f"\n{'='*60}")
    print(f"TASK: {task.id}")
    print(f"{'='*60}")
    print(f"Title:       {task.title}")
    print(f"Type:        {task.task_type.value}")
    print(f"Status:      {task.status.value}")
    print(f"Agent:       {task.agent_type.value}")
    print(f"Depends on:  {', '.join(task.depends_on) or 'None'}")
    print(f"Review:      {'Required' if task.requires_review else 'Skipped'}")
    print(f"Approval:    {'Required' if task.requires_human_approval else 'Auto'}")
    print(f"Red Team:    {'Required' if task.requires_redteam else 'Optional'}")
    print(f"QA:          {'Required' if task.requires_qa else 'Optional'}")
    
    if task.loop_config.enabled:
        print(f"\n--- FEEDBACK LOOP ---")
        print(f"Enabled:     Yes")
        print(f"Max iter:    {task.loop_config.max_iterations}")
        print(f"Current:     {task.loop_state.iteration}")
        print(f"Reviewer:    {'✓' if task.loop_config.require_reviewer else '✗'} (min score: {task.loop_config.min_review_score})")
        print(f"QA:          {'✓' if task.loop_config.require_qa else '✗'}")
        print(f"Red Team:    {'✓' if task.loop_config.require_redteam else '✗'}")
        if task.loop_state.review_scores:
            print(f"Scores:      {' → '.join(f'{s:.2f}' for s in task.loop_state.review_scores)}")
        if task.loop_state.qa_results:
            print(f"QA Results:  {' → '.join(task.loop_state.qa_results)}")
    
    if task.input_contract:
        print(f"\n--- INPUT CONTRACT ---")
        print(task.input_contract)
    
    if task.output_contract:
        print(f"\n--- OUTPUT CONTRACT ---")
        print(task.output_contract)
    
    if task.acceptance_criteria:
        print(f"\n--- ACCEPTANCE CRITERIA ---")
        for criterion in task.acceptance_criteria:
            print(f"  • {criterion}")
    
    print(f"\n--- PROMPT ---")
    print(task.prompt[:500] + "..." if len(task.prompt) > 500 else task.prompt)
    
    print(f"{'='*60}\n")


def cmd_export_done(args):
    """Export approved artifacts for air-gapped transfer."""
    engine = get_engine()
    
    try:
        export_path = engine.export_done(
            output_file=args.output,
            include_reports=not args.no_reports
        )
        
        print(f"\n✅ Export complete!")
        print(f"   File: {export_path}")
        print(f"\n   This bundle can be transferred across the data diode.")
        print(f"   Contents include all approved artifacts and security sign-offs.\n")
        
    except Exception as e:
        print(f"Error creating export: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Agent Workflow Engine CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # status
    subparsers.add_parser("status", help="Show workflow status")
    
    # list
    subparsers.add_parser("list", help="List all tasks")
    
    # validate
    subparsers.add_parser("validate", help="Validate workflow")
    
    # show
    show_parser = subparsers.add_parser("show", help="Show task details")
    show_parser.add_argument("task_id", help="Task ID to show")
    
    # contracts
    contracts_parser = subparsers.add_parser("contracts", help="Generate contracts")
    contracts_parser.add_argument("feature", help="Feature description")
    contracts_parser.add_argument("--output", "-o", help="Output filename")
    
    # plan
    plan_parser = subparsers.add_parser("plan", help="Decompose goal into tasks")
    plan_parser.add_argument("goal", help="High-level goal")
    plan_parser.add_argument("--output", "-o", help="Output filename")
    
    # redteam
    redteam_parser = subparsers.add_parser("redteam", help="Run red team analysis")
    redteam_parser.add_argument("target", help="Task ID or file path")
    redteam_parser.add_argument("--output", "-o", help="Output filename")
    
    # qa
    qa_parser = subparsers.add_parser("qa", help="Run QA verification")
    qa_parser.add_argument("target", help="Task ID or file path")
    qa_parser.add_argument("--output", "-o", help="Output filename")
    
    # run
    run_parser = subparsers.add_parser("run", help="Run a specific task")
    run_parser.add_argument("task_id", help="Task ID to run")
    
    # run-next
    subparsers.add_parser("run-next", help="Run the next available task")
    
    # run-all
    subparsers.add_parser("run-all", help="Run all tasks until review needed")
    
    # review
    subparsers.add_parser("review", help="Show tasks pending review")
    
    # approve
    approve_parser = subparsers.add_parser("approve", help="Approve a reviewed task")
    approve_parser.add_argument("task_id", help="Task ID to approve")
    
    # reject
    reject_parser = subparsers.add_parser("reject", help="Reject a task")
    reject_parser.add_argument("task_id", help="Task ID to reject")
    reject_parser.add_argument("--reason", "-r", help="Rejection reason")
    
    # export-done
    export_parser = subparsers.add_parser("export-done", 
        help="Export approved artifacts for air-gapped transfer")
    export_parser.add_argument("--output", "-o", 
        help="Output filename (default: export-TIMESTAMP.zip)")
    export_parser.add_argument("--no-reports", action="store_true",
        help="Exclude QA and Red Team reports from export")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    commands = {
        "status": cmd_status,
        "list": cmd_list,
        "validate": cmd_validate,
        "show": cmd_show,
        "contracts": cmd_contracts,
        "plan": cmd_plan,
        "redteam": cmd_redteam,
        "qa": cmd_qa,
        "run": cmd_run,
        "run-next": cmd_run_next,
        "run-all": cmd_run_all,
        "review": cmd_review,
        "approve": cmd_approve,
        "reject": cmd_reject,
        "export-done": cmd_export_done,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
