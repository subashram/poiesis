"""
Workflow Engine - orchestrates agents and manages task execution.
"""
import json
import yaml
import shutil
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Optional

from .models import (
    Task, TaskStatus, TaskType, AgentConfig, AgentType, 
    WorkflowState, ReviewResult, QAResult, LoopConfig, LoopState
)
from .llm_client import LLMClient
from .context_retriever import ContextRetriever


# Threshold for using smart retrieval vs full context (in chars)
SMART_RETRIEVAL_THRESHOLD = 20000  # ~5K tokens


class WorkflowEngine:
    """
    Orchestrates the execution of tasks through specialized agents.
    
    Supports the Feedback Loop (Rework Loop):
    Developer → Reviewer → Red Team → QA → [Pass?] → Human Review
                                        ↓ No
                                    Back to Developer
    
    Context Retrieval:
    - For small doc sets (<20K chars): loads all context
    - For large doc sets: uses smart retrieval to select relevant sections
    """
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.config_path = self.base_path / "config"
        self.design_path = self.base_path / "design"
        self.contracts_path = self.base_path / "contracts"
        self.tasks_path = self.base_path / "tasks"
        self.artifacts_path = self.base_path / "artifacts"
        self.review_path = self.base_path / "review"
        self.redteam_path = self.base_path / "redteam"
        self.qa_path = self.base_path / "qa"
        self.done_path = self.base_path / "done"
        self.exports_path = self.base_path / "exports"
        self.state_file = self.base_path / "workflow_state.json"
        
        # Ensure directories exist
        for path in [self.config_path, self.design_path, self.contracts_path,
                     self.tasks_path, self.artifacts_path, self.review_path, 
                     self.redteam_path, self.qa_path, self.done_path, 
                     self.exports_path]:
            path.mkdir(parents=True, exist_ok=True)
        
        self.agents: dict[AgentType, AgentConfig] = {}
        self.state = WorkflowState()
        self.llm_client: Optional[LLMClient] = None
        
        # Context management
        self.context_retriever: Optional[ContextRetriever] = None
        self.full_context: Optional[str] = None
        self.use_smart_retrieval: bool = False
        self.total_context_size: int = 0
        
    def initialize(self):
        """Load agents, design docs, and restore state."""
        self._load_agents()
        self._load_context()
        self._load_state()
        self._load_tasks()
        self.llm_client = LLMClient()
        
    def _load_agents(self):
        """Load agent configurations from config directory."""
        for config_file in self.config_path.glob("*.yaml"):
            # Skip template and examples
            if "template" in config_file.name or config_file.parent.name == "examples":
                continue
            with open(config_file) as f:
                data = yaml.safe_load(f)
                if data and "agent_type" in data:
                    agent = AgentConfig.from_dict(data)
                    self.agents[agent.agent_type] = agent
                    print(f"  Loaded agent: {agent.name} ({agent.agent_type.value})")
    
    def _load_context(self):
        """
        Load design documents with smart retrieval support.
        
        - If total docs < threshold: load all (fast, simple)
        - If total docs > threshold: use retriever (relevant sections only)
        """
        # Initialize retriever
        self.context_retriever = ContextRetriever(self.design_path, self.contracts_path)
        chunk_count = self.context_retriever.load()
        
        # Calculate total context size
        self.total_context_size = sum(len(c.content) for c in self.context_retriever.chunks)
        
        if self.total_context_size == 0:
            print("  No design documents found in design/")
            return
        
        # Decide retrieval strategy
        if self.total_context_size > SMART_RETRIEVAL_THRESHOLD:
            self.use_smart_retrieval = True
            print(f"  📚 Loaded {chunk_count} sections ({self.total_context_size:,} chars)")
            print(f"  🔍 Smart retrieval ENABLED (docs exceed {SMART_RETRIEVAL_THRESHOLD:,} char threshold)")
        else:
            self.use_smart_retrieval = False
            self.full_context = self.context_retriever.get_full_context()
            print(f"  📄 Loaded full context ({self.total_context_size:,} chars)")
            print(f"  📋 Using full context (below {SMART_RETRIEVAL_THRESHOLD:,} char threshold)")
    
    def _get_context_for_task(self, task: Task) -> Optional[str]:
        """
        Get relevant context for a task.
        
        Uses smart retrieval for large doc sets, full context for small ones.
        """
        if not self.context_retriever or self.total_context_size == 0:
            return None
        
        if self.use_smart_retrieval:
            # Retrieve only relevant sections
            context = self.context_retriever.retrieve_for_task(task)
            if context:
                return f"# RELEVANT DESIGN CONTEXT\n\n{context}"
            return None
        else:
            # Use full context
            return f"# DESIGN CONTEXT\n\n{self.full_context}"
    
    def _load_state(self):
        """Load workflow state from file."""
        if self.state_file.exists():
            with open(self.state_file) as f:
                data = json.load(f)
                self.state.completed_tasks = data.get("completed_tasks", [])
                self.state.current_task = data.get("current_task")
                
    def _save_state(self):
        """Persist workflow state."""
        data = {
            "completed_tasks": self.state.completed_tasks,
            "current_task": self.state.current_task,
            "tasks": {
                task_id: task.to_dict() 
                for task_id, task in self.state.tasks.items()
            }
        }
        with open(self.state_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def _load_tasks(self):
        """Load task definitions from tasks directory."""
        for task_file in sorted(self.tasks_path.glob("*.yaml")):
            with open(task_file) as f:
                data = yaml.safe_load(f)
                task = Task.from_dict(data)
                
                if task.id in self.state.completed_tasks:
                    task.status = TaskStatus.COMPLETED
                elif (self.review_path / f"{task.id}.md").exists():
                    task.status = TaskStatus.REVIEW
                    
                self.state.tasks[task.id] = task
                
    def get_status(self) -> dict:
        """Get current workflow status."""
        tasks_in_loop = self.state.get_tasks_in_loop()
        
        status = {
            "total_tasks": len(self.state.tasks),
            "completed": len(self.state.completed_tasks),
            "pending": 0,
            "in_review": 0,
            "in_loop": len(tasks_in_loop),
            "ready": [],
            "context_size": self.total_context_size,
            "smart_retrieval": self.use_smart_retrieval,
            "has_qa": AgentType.QA in self.agents,
            "has_redteam": AgentType.REDTEAM in self.agents,
            "contract_tasks": len(self.state.get_tasks_by_type(TaskType.CONTRACT)),
            "implementation_tasks": len(self.state.get_tasks_by_type(TaskType.IMPLEMENTATION)),
        }
        
        for task in self.state.tasks.values():
            if task.status == TaskStatus.PENDING:
                status["pending"] += 1
            elif task.status == TaskStatus.REVIEW:
                status["in_review"] += 1
            elif task.status == TaskStatus.REWORK:
                status["pending"] += 1
                
        status["ready"] = [t.id for t in self.state.get_ready_tasks()]
        return status
    
    def validate_workflow(self) -> list[str]:
        """Validate workflow ordering and contract definitions."""
        warnings = self.state.validate_workflow_order()
        
        for task in self.state.tasks.values():
            for dep in task.depends_on:
                if dep not in self.state.tasks:
                    warnings.append(f"❌ {task.id}: Depends on unknown task '{dep}'")
        
        # Check for circular dependencies
        for task in self.state.tasks.values():
            visited = set()
            queue = list(task.depends_on)
            while queue:
                dep_id = queue.pop(0)
                if dep_id == task.id:
                    warnings.append(f"❌ {task.id}: Circular dependency detected")
                    break
                if dep_id in visited:
                    continue
                visited.add(dep_id)
                if dep_id in self.state.tasks:
                    queue.extend(self.state.tasks[dep_id].depends_on)
        
        return warnings
    
    def run_task(self, task_id: str, skip_contract_warning: bool = False) -> bool:
        """Execute a single task, potentially with feedback loop."""
        if task_id not in self.state.tasks:
            print(f"Task not found: {task_id}")
            return False
            
        task = self.state.tasks[task_id]
        
        # Check dependencies
        for dep in task.depends_on:
            if dep not in self.state.completed_tasks:
                print(f"Dependency not met: {dep}")
                return False
        
        # Get the appropriate agent
        if task.agent_type not in self.agents:
            print(f"No agent configured for type: {task.agent_type.value}")
            return False
        
        # Warn about missing contracts
        if (task.task_type == TaskType.IMPLEMENTATION and 
            not skip_contract_warning and
            not task.input_contract and 
            not task.output_contract and
            not task.contract_task):
            print(f"\n⚠️  WARNING: Implementation task '{task_id}' has no contracts.")
            print("   Continuing anyway...\n")
        
        # If loop is enabled, run with feedback loop
        if task.loop_config.enabled:
            return self._run_with_loop(task)
        else:
            return self._run_single(task)
    
    def _run_single(self, task: Task) -> bool:
        """Run a task without feedback loop."""
        agent = self.agents[task.agent_type]
        
        print(f"\n{'='*60}")
        print(f"Running task: {task.title}")
        print(f"Type: {task.task_type.value}")
        print(f"Agent: {agent.name}")
        if self.use_smart_retrieval:
            print(f"Context: Smart retrieval enabled")
        print(f"{'='*60}\n")
        
        task.status = TaskStatus.RUNNING
        self.state.current_task = task.id
        self._save_state()
        
        context = self._build_full_context(task)
        
        try:
            artifact = self.llm_client.generate(
                agent_config=agent,
                user_prompt=task.prompt,
                context=context,
            )
        except Exception as e:
            print(f"Error generating artifact: {e}")
            task.status = TaskStatus.FAILED
            self._save_state()
            return False
        
        # Save artifact
        self._save_artifact(task, artifact, agent.name)
        
        # Run automated checks
        if task.requires_review and AgentType.REVIEWER in self.agents:
            review_result = self._run_review(task, artifact)
            print(f"\nReview Score: {review_result['score']:.2f}")
        
        if task.requires_redteam and AgentType.REDTEAM in self.agents:
            print("\n🔴 Running Red Team analysis...")
            redteam_report = self._run_redteam(task, artifact)
            task.redteam_report = redteam_report
            self._save_redteam_report(task, redteam_report)
        
        if task.requires_qa and AgentType.QA in self.agents:
            print("\n🧪 Running QA verification...")
            qa_report = self._run_qa(task, artifact)
            task.qa_report = qa_report
            self._save_qa_report(task, qa_report)
        
        # Queue for human review
        if task.requires_human_approval:
            self._queue_for_review(task, artifact)
            task.status = TaskStatus.REVIEW
            print(f"\n📋 Task queued for human review: {self.review_path}/{task.id}.md")
        else:
            self._complete_task(task)
            
        self._save_state()
        return True
    
    def _run_with_loop(self, task: Task) -> bool:
        """
        Run a task with the feedback loop (Rework Loop).
        """
        config = task.loop_config
        state = task.loop_state
        
        print(f"\n{'='*60}")
        print(f"🔄 FEEDBACK LOOP ENABLED")
        print(f"Task: {task.title}")
        print(f"Max iterations: {config.max_iterations}")
        if self.use_smart_retrieval:
            print(f"Context: Smart retrieval enabled")
        print(f"{'='*60}\n")
        
        while state.iteration < config.max_iterations:
            iteration = state.iteration + 1
            print(f"\n{'─'*40}")
            print(f"📍 Iteration {iteration}/{config.max_iterations}")
            print(f"{'─'*40}")
            
            # Step 1: Generate/Fix artifact
            artifact = self._generate_or_fix(task, state)
            if artifact is None:
                task.status = TaskStatus.FAILED
                self._save_state()
                return False
            
            self._save_artifact(task, artifact, self.agents[task.agent_type].name, iteration)
            
            # Step 2: Run checks and collect feedback
            feedback_parts = []
            review_score = None
            qa_status = None
            redteam_critical = 0
            
            # Reviewer
            if config.require_reviewer and AgentType.REVIEWER in self.agents:
                print("\n✅ Running Reviewer...")
                review_result = self._run_review(task, artifact)
                review_score = review_result["score"]
                print(f"   Score: {review_score:.2f}")
                
                if review_score < config.min_review_score:
                    feedback_parts.append(f"## Reviewer Feedback (Score: {review_score:.2f})\n\n")
                    feedback_parts.append(review_result["feedback"])
                    if review_result["issues"]:
                        feedback_parts.append("\n\nIssues:\n- " + "\n- ".join(review_result["issues"]))
            
            # Red Team
            if config.require_redteam and AgentType.REDTEAM in self.agents:
                print("\n🔴 Running Red Team...")
                redteam_report = self._run_redteam(task, artifact)
                task.redteam_report = redteam_report
                
                redteam_critical = redteam_report.lower().count("critical")
                print(f"   Critical issues: ~{redteam_critical}")
                
                if redteam_critical > config.redteam_max_critical:
                    feedback_parts.append(f"\n\n## Red Team Findings ({redteam_critical} critical)\n\n")
                    feedback_parts.append(redteam_report[:2000])
            
            # QA
            if config.require_qa and AgentType.QA in self.agents:
                print("\n🧪 Running QA...")
                qa_report = self._run_qa(task, artifact)
                task.qa_report = qa_report
                
                if "PASS" in qa_report.upper() and "FAIL" not in qa_report.upper():
                    qa_status = "PASS"
                elif "FAIL" in qa_report.upper():
                    qa_status = "FAIL"
                else:
                    qa_status = "NEEDS_WORK"
                print(f"   Status: {qa_status}")
                
                if qa_status != "PASS" and config.qa_must_pass:
                    feedback_parts.append(f"\n\n## QA Report (Status: {qa_status})\n\n")
                    feedback_parts.append(qa_report[:2000])
            
            # Record iteration
            state.add_iteration(
                review_score=review_score,
                qa_result=qa_status,
                redteam_critical=redteam_critical,
                feedback="\n".join(feedback_parts) if feedback_parts else None
            )
            
            # Check if all pass
            all_pass = True
            if config.require_reviewer and review_score is not None:
                if review_score < config.min_review_score:
                    all_pass = False
            if config.require_qa and config.qa_must_pass:
                if qa_status != "PASS":
                    all_pass = False
            if config.require_redteam:
                if redteam_critical > config.redteam_max_critical:
                    all_pass = False
            
            if all_pass:
                print(f"\n✅ All checks passed on iteration {iteration}!")
                break
            else:
                print(f"\n🔄 Iteration {iteration} needs rework...")
                if iteration >= config.max_iterations:
                    print(f"\n⚠️  Max iterations ({config.max_iterations}) reached.")
                    print("   Proceeding to human review despite issues.")
        
        self._save_state()
        
        if task.redteam_report:
            self._save_redteam_report(task, task.redteam_report)
        if task.qa_report:
            self._save_qa_report(task, task.qa_report)
        
        if task.requires_human_approval:
            self._queue_for_review(task, artifact, include_loop_history=True)
            task.status = TaskStatus.REVIEW
            print(f"\n📋 Task queued for human review: {self.review_path}/{task.id}.md")
        else:
            self._complete_task(task)
        
        self._save_state()
        return True
    
    def _generate_or_fix(self, task: Task, state: LoopState) -> Optional[str]:
        """Generate initial artifact or fix based on feedback."""
        agent = self.agents[task.agent_type]
        context = self._build_full_context(task)
        
        if state.iteration == 0:
            prompt = task.prompt
        else:
            previous_artifact = self._get_latest_artifact(task)
            feedback = state.feedback_history[-1] if state.feedback_history else ""
            
            prompt = f"""## Original Task
{task.prompt}

## Previous Implementation (Iteration {state.iteration})
```
{previous_artifact[:8000] if previous_artifact else "Not available"}
```

## Feedback from Automated Checks
{feedback}

## Instructions
Fix the issues identified in the feedback. Produce an improved implementation that:
1. Addresses all reviewer concerns
2. Fixes any QA failures
3. Resolves security issues from red team

Output the COMPLETE fixed implementation, not just the changes.
"""
        
        try:
            return self.llm_client.generate(
                agent_config=agent,
                user_prompt=prompt,
                context=context,
            )
        except Exception as e:
            print(f"Error generating artifact: {e}")
            return None
    
    def _get_latest_artifact(self, task: Task) -> Optional[str]:
        """Get the most recent artifact for a task."""
        for i in range(task.loop_state.iteration, 0, -1):
            artifact_file = self.artifacts_path / f"{task.id}-iter{i}.md"
            if artifact_file.exists():
                with open(artifact_file) as f:
                    return f.read()
        
        artifact_file = self.artifacts_path / f"{task.id}.md"
        if artifact_file.exists():
            with open(artifact_file) as f:
                return f.read()
        return None
    
    def _save_artifact(self, task: Task, artifact: str, agent_name: str, iteration: int = None):
        """Save artifact to file."""
        if iteration:
            filename = f"{task.id}-iter{iteration}.md"
        else:
            filename = f"{task.id}.md"
        
        artifact_file = self.artifacts_path / filename
        with open(artifact_file, "w") as f:
            f.write(f"# {task.title}\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
            f.write(f"Task Type: {task.task_type.value}\n")
            f.write(f"Agent: {agent_name}\n")
            if iteration:
                f.write(f"Iteration: {iteration}\n")
            f.write("\n---\n\n")
            f.write(artifact)
        
        task.artifact_path = str(artifact_file)
    
    def _save_redteam_report(self, task: Task, report: str):
        """Save red team report."""
        report_file = self.redteam_path / f"{task.id}-redteam.md"
        with open(report_file, "w") as f:
            f.write(f"# Red Team Report: {task.title}\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n\n---\n\n")
            f.write(report)
    
    def _save_qa_report(self, task: Task, report: str):
        """Save QA report."""
        report_file = self.qa_path / f"{task.id}-qa.md"
        with open(report_file, "w") as f:
            f.write(f"# QA Report: {task.title}\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n\n---\n\n")
            f.write(report)
    
    def _build_full_context(self, task: Task) -> Optional[str]:
        """Build complete context for a task using smart retrieval."""
        context_parts = []
        
        # Get design context (smart or full)
        design_context = self._get_context_for_task(task)
        if design_context:
            context_parts.append(design_context)
        
        # Dependency artifacts
        dep_context = self._gather_dependency_context(task)
        if dep_context:
            context_parts.append("# COMPLETED DEPENDENCIES\n\n" + dep_context)
        
        # Contract from contract task
        if task.contract_task:
            contract_context = self._get_contract_context(task.contract_task)
            if contract_context:
                context_parts.append(f"# CONTRACT (from {task.contract_task})\n\n{contract_context}")
        
        # Inline contracts
        if task.input_contract:
            context_parts.append(f"# INPUT CONTRACT\n\n{task.input_contract}")
        
        if task.output_contract:
            context_parts.append(f"# OUTPUT CONTRACT\n\n{task.output_contract}")
        
        # Acceptance criteria
        if task.acceptance_criteria:
            criteria_text = "\n".join(f"- {c}" for c in task.acceptance_criteria)
            context_parts.append(f"# ACCEPTANCE CRITERIA\n\n{criteria_text}")
        
        if not context_parts:
            return None
            
        return "\n\n" + "="*60 + "\n\n".join(context_parts)
    
    def _get_contract_context(self, contract_task_id: str) -> Optional[str]:
        """Get the artifact from a contract task."""
        for folder in [self.done_path, self.artifacts_path, self.contracts_path]:
            contract_file = folder / f"{contract_task_id}.md"
            if contract_file.exists():
                with open(contract_file) as f:
                    return f.read()
        return None
    
    def _gather_dependency_context(self, task: Task) -> Optional[str]:
        """Gather context from completed dependency artifacts."""
        if not task.depends_on:
            return None
            
        context_parts = []
        for dep_id in task.depends_on:
            artifact_file = self.done_path / f"{dep_id}.md"
            if not artifact_file.exists():
                artifact_file = self.artifacts_path / f"{dep_id}.md"
            
            if artifact_file.exists():
                with open(artifact_file) as f:
                    context_parts.append(f"## {dep_id}\n\n{f.read()}")
                    
        return "\n\n---\n\n".join(context_parts) if context_parts else None
    
    def _run_review(self, task: Task, artifact: str) -> dict:
        """Run automated review on an artifact."""
        reviewer = self.agents[AgentType.REVIEWER]
        
        review_context = ""
        if task.output_contract:
            review_context = f"\n\n## Expected Output Contract\n{task.output_contract}"
        if task.acceptance_criteria:
            criteria_text = "\n".join(f"- {c}" for c in task.acceptance_criteria)
            review_context += f"\n\n## Acceptance Criteria\n{criteria_text}"
        
        return self.llm_client.review(
            reviewer_config=reviewer,
            artifact=artifact,
            original_task=task.prompt + review_context,
        )
    
    def _run_redteam(self, task: Task, artifact: str) -> str:
        """Run red team analysis on an artifact."""
        redteam = self.agents[AgentType.REDTEAM]
        
        # Get relevant context for red team
        context = self._get_context_for_task(task)
        
        prompt = f"""## Original Task
{task.prompt}

## Artifact to Attack
```
{artifact}
```

## Your Mission
Analyze this artifact for security vulnerabilities, edge cases, and failure modes.
Think like an attacker. Find what breaks.
"""
        
        return self.llm_client.generate(
            agent_config=redteam,
            user_prompt=prompt,
            context=context,
        )
    
    def _run_qa(self, task: Task, artifact: str) -> str:
        """Run QA verification on an artifact."""
        qa = self.agents[AgentType.QA]
        
        # Get relevant context for QA
        context = self._get_context_for_task(task)
        
        criteria_text = ""
        if task.acceptance_criteria:
            criteria_text = "\n".join(f"- {c}" for c in task.acceptance_criteria)
        
        prompt = f"""## Task
{task.prompt}

## Output Contract
{task.output_contract or "Not specified"}

## Acceptance Criteria
{criteria_text or "Not specified"}

## Implementation to Verify
```
{artifact}
```

## Your Mission
Verify this implementation meets its contract and acceptance criteria.
Generate test cases. Identify edge cases that aren't handled.
"""
        
        return self.llm_client.generate(
            agent_config=qa,
            user_prompt=prompt,
            context=context,
        )
    
    def _queue_for_review(self, task: Task, artifact: str, include_loop_history: bool = False):
        """Place artifact in review queue for human approval."""
        review_file = self.review_path / f"{task.id}.md"
        with open(review_file, "w") as f:
            f.write(f"# Review: {task.title}\n\n")
            f.write(f"Task ID: {task.id}\n")
            f.write(f"Task Type: {task.task_type.value}\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
            
            if include_loop_history and task.loop_config.enabled:
                state = task.loop_state
                f.write(f"\n## 🔄 Feedback Loop Summary\n\n")
                f.write(f"- Iterations: {state.iteration}\n")
                if state.review_scores:
                    f.write(f"- Review scores: {' → '.join(f'{s:.2f}' for s in state.review_scores)}\n")
                if state.qa_results:
                    f.write(f"- QA results: {' → '.join(state.qa_results)}\n")
                if state.redteam_critical_counts:
                    f.write(f"- Red team critical: {' → '.join(str(c) for c in state.redteam_critical_counts)}\n")
            
            f.write("\n")
            
            if task.input_contract:
                f.write("## Input Contract\n\n")
                f.write(f"{task.input_contract}\n\n")
            
            if task.output_contract:
                f.write("## Expected Output Contract\n\n")
                f.write(f"{task.output_contract}\n\n")
            
            if task.acceptance_criteria:
                f.write("## Acceptance Criteria\n\n")
                for c in task.acceptance_criteria:
                    f.write(f"- {c}\n")
                f.write("\n")
            
            f.write("## Original Task\n\n")
            f.write(f"{task.prompt}\n\n")
            
            f.write("## Generated Artifact\n\n")
            f.write(artifact)
            
            if task.redteam_report:
                f.write("\n\n---\n\n## 🔴 RED TEAM REPORT\n\n")
                f.write(task.redteam_report)
            
            if task.qa_report:
                f.write("\n\n---\n\n## 🧪 QA REPORT\n\n")
                f.write(task.qa_report)
            
            f.write("\n\n---\n\n## Review Actions\n\n")
            f.write(f"To approve: `python cli.py approve {task.id}`\n")
            f.write(f"To reject: `python cli.py reject {task.id} --reason 'your feedback'`\n")
    
    def approve_task(self, task_id: str) -> bool:
        """Approve a task in review."""
        if task_id not in self.state.tasks:
            print(f"Task not found: {task_id}")
            return False
            
        task = self.state.tasks[task_id]
        
        if task.status != TaskStatus.REVIEW:
            print(f"Task not in review: {task_id}")
            return False
        
        review_file = self.review_path / f"{task_id}.md"
        
        if task.task_type == TaskType.CONTRACT:
            done_file = self.contracts_path / f"{task_id}.md"
        else:
            done_file = self.done_path / f"{task_id}.md"
        
        if review_file.exists():
            shutil.move(str(review_file), str(done_file))
            
        self._complete_task(task)
        self._save_state()
        
        print(f"✅ Approved: {task.title}")
        if task.loop_config.enabled:
            print(f"   Completed in {task.loop_state.iteration} iteration(s)")
        
        return True
    
    def reject_task(self, task_id: str, reason: str) -> bool:
        """Reject a task and queue for rework."""
        if task_id not in self.state.tasks:
            print(f"Task not found: {task_id}")
            return False
            
        task = self.state.tasks[task_id]
        task.status = TaskStatus.REJECTED
        task.review_feedback = reason
        
        review_file = self.review_path / f"{task_id}.md"
        if review_file.exists():
            review_file.unlink()
            
        self._save_state()
        
        print(f"❌ Rejected: {task.title}")
        print(f"   Reason: {reason}")
        return True
    
    def _complete_task(self, task: Task):
        """Mark a task as completed."""
        task.status = TaskStatus.COMPLETED
        task.updated_at = datetime.now()
        self.state.completed_tasks.append(task.id)
        self.state.current_task = None
        
    def list_review_queue(self) -> list[dict]:
        """List all tasks pending human review."""
        items = []
        for task_id, task in self.state.tasks.items():
            if task.status == TaskStatus.REVIEW:
                items.append({
                    "id": task_id,
                    "title": task.title,
                    "task_type": task.task_type.value,
                    "has_redteam": task.redteam_report is not None,
                    "has_qa": task.qa_report is not None,
                    "loop_iterations": task.loop_state.iteration if task.loop_config.enabled else 0,
                    "file": str(self.review_path / f"{task_id}.md"),
                })
        return items
    
    # =========================================================================
    # Export for Air-Gapped Transfer
    # =========================================================================
    
    def export_done(self, output_file: Optional[str] = None, 
                    include_reports: bool = True) -> str:
        """
        Export all approved artifacts for air-gapped transfer.
        
        Creates a ZIP bundle containing:
        - All approved artifacts from done/
        - All contracts from contracts/
        - QA reports (if include_reports)
        - Red Team reports (if include_reports)
        - Manifest with metadata
        
        Args:
            output_file: Output filename (default: export-TIMESTAMP.zip)
            include_reports: Include QA and Red Team reports
            
        Returns:
            Path to the created export file
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        
        if output_file:
            export_file = self.exports_path / output_file
        else:
            export_file = self.exports_path / f"export-{timestamp}.zip"
        
        # Collect files to export
        files_to_export = []
        manifest = {
            "export_timestamp": timestamp,
            "engine_version": "1.0.0",
            "artifacts": [],
            "contracts": [],
            "qa_reports": [],
            "redteam_reports": [],
        }
        
        # Approved artifacts
        for artifact_file in sorted(self.done_path.glob("*.md")):
            if artifact_file.name == ".gitkeep":
                continue
            files_to_export.append(("artifacts", artifact_file))
            manifest["artifacts"].append({
                "file": artifact_file.name,
                "task_id": artifact_file.stem,
            })
        
        # Contracts
        for contract_file in sorted(self.contracts_path.glob("*.md")):
            if contract_file.name == ".gitkeep":
                continue
            files_to_export.append(("contracts", contract_file))
            manifest["contracts"].append({
                "file": contract_file.name,
            })
        
        # Reports
        if include_reports:
            for qa_file in sorted(self.qa_path.glob("*.md")):
                files_to_export.append(("reports/qa", qa_file))
                manifest["qa_reports"].append({"file": qa_file.name})
            
            for rt_file in sorted(self.redteam_path.glob("*.md")):
                files_to_export.append(("reports/redteam", rt_file))
                manifest["redteam_reports"].append({"file": rt_file.name})
        
        # Task metadata
        manifest["tasks"] = {}
        for task_id in self.state.completed_tasks:
            if task_id in self.state.tasks:
                task = self.state.tasks[task_id]
                manifest["tasks"][task_id] = {
                    "title": task.title,
                    "type": task.task_type.value,
                    "loop_iterations": task.loop_state.iteration if task.loop_config.enabled else 0,
                }
        
        # Create ZIP
        with zipfile.ZipFile(export_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add manifest
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            
            # Add files
            for folder, file_path in files_to_export:
                arcname = f"{folder}/{file_path.name}"
                zf.write(file_path, arcname)
            
            # Add README
            readme = self._generate_export_readme(manifest)
            zf.writestr("README.md", readme)
        
        print(f"📦 Export created: {export_file}")
        print(f"   Artifacts: {len(manifest['artifacts'])}")
        print(f"   Contracts: {len(manifest['contracts'])}")
        if include_reports:
            print(f"   QA Reports: {len(manifest['qa_reports'])}")
            print(f"   Red Team Reports: {len(manifest['redteam_reports'])}")
        
        return str(export_file)
    
    def _generate_export_readme(self, manifest: dict) -> str:
        """Generate a README for the export bundle."""
        lines = [
            "# Agent Workflow Export",
            "",
            f"Exported: {manifest['export_timestamp']}",
            "",
            "## Contents",
            "",
            "### Artifacts",
            "",
        ]
        
        for artifact in manifest["artifacts"]:
            task_info = manifest["tasks"].get(artifact["task_id"], {})
            title = task_info.get("title", artifact["task_id"])
            lines.append(f"- `artifacts/{artifact['file']}` - {title}")
        
        lines.extend([
            "",
            "### Contracts",
            "",
        ])
        
        for contract in manifest["contracts"]:
            lines.append(f"- `contracts/{contract['file']}`")
        
        if manifest.get("qa_reports"):
            lines.extend([
                "",
                "### QA Reports",
                "",
            ])
            for report in manifest["qa_reports"]:
                lines.append(f"- `reports/qa/{report['file']}`")
        
        if manifest.get("redteam_reports"):
            lines.extend([
                "",
                "### Security Reports (Red Team)",
                "",
            ])
            for report in manifest["redteam_reports"]:
                lines.append(f"- `reports/redteam/{report['file']}`")
        
        lines.extend([
            "",
            "## Verification",
            "",
            "All artifacts in this bundle have been:",
            "- Generated by the Agent Workflow Engine",
            "- Reviewed by automated agents (Reviewer, QA, Red Team)",
            "- Approved by a human operator",
            "",
            "See `manifest.json` for full metadata.",
        ])
        
        return "\n".join(lines)
    
    # =========================================================================
    # Contract and Planning
    # =========================================================================
    
    def generate_contracts(self, feature: str, output_file: Optional[str] = None) -> str:
        """Generate contracts for a feature."""
        if AgentType.CONTRACT not in self.agents:
            raise ValueError("No contract agent configured.")
        
        contract_agent = self.agents[AgentType.CONTRACT]
        
        # Get relevant context
        context = None
        if self.context_retriever:
            chunks = self.context_retriever.retrieve(feature, max_chunks=10)
            if chunks:
                context = "# RELEVANT DESIGN CONTEXT\n\n"
                context += "\n\n".join(f"## {c.source}: {c.section}\n{c.content}" for c in chunks)
        
        prompt = f"""## Feature
{feature}

## Instructions
Define the contracts for this feature BEFORE any implementation begins.
Be precise and specific. These contracts will be used by implementation agents.
"""
        
        result = self.llm_client.generate(
            agent_config=contract_agent,
            user_prompt=prompt,
            context=context,
        )
        
        if output_file:
            output_path = self.contracts_path / output_file
            with open(output_path, "w") as f:
                f.write(f"# Contracts: {feature}\n\n")
                f.write(f"Generated: {datetime.now().isoformat()}\n\n---\n\n")
                f.write(result)
            print(f"📜 Contracts saved to: {output_path}")
        
        return result
    
    def plan_feature(self, goal: str, output_file: Optional[str] = None) -> str:
        """Decompose a goal into tasks."""
        if AgentType.PLANNER not in self.agents:
            raise ValueError("No planner agent configured.")
        
        planner = self.agents[AgentType.PLANNER]
        
        # Get relevant context
        context = None
        if self.context_retriever:
            chunks = self.context_retriever.retrieve(goal, max_chunks=10)
            if chunks:
                context = "# RELEVANT DESIGN CONTEXT\n\n"
                context += "\n\n".join(f"## {c.source}: {c.section}\n{c.content}" for c in chunks)
        
        prompt = f"""## Goal
{goal}

## Instructions
Break this goal into atomic, contract-driven tasks.
Start with CONTRACT tasks first, then IMPLEMENTATION tasks.

For tasks that benefit from automated iteration, add a loop configuration:
```yaml
loop:
  enabled: true
  max_iterations: 3
  require_reviewer: true
  require_qa: true
  require_redteam: false  # Enable for security-critical tasks
```

Output the tasks in YAML format.
"""
        
        result = self.llm_client.generate(
            agent_config=planner,
            user_prompt=prompt,
            context=context,
        )
        
        if output_file:
            output_path = self.tasks_path / output_file
            with open(output_path, "w") as f:
                f.write(result)
            print(f"📝 Tasks saved to: {output_path}")
        
        return result
    
    def redteam_artifact(self, artifact_path: str, output_file: Optional[str] = None) -> str:
        """Run red team analysis on any artifact file."""
        if AgentType.REDTEAM not in self.agents:
            raise ValueError("No red team agent configured.")
        
        path = Path(artifact_path)
        if not path.is_absolute():
            for folder in [self.artifacts_path, self.done_path, self.base_path]:
                if (folder / artifact_path).exists():
                    path = folder / artifact_path
                    break
        
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {artifact_path}")
        
        with open(path) as f:
            artifact = f.read()
        
        redteam = self.agents[AgentType.REDTEAM]
        
        # Get relevant context
        context = None
        if self.context_retriever:
            chunks = self.context_retriever.retrieve(artifact[:1000], max_chunks=5)
            if chunks:
                context = "# RELEVANT DESIGN CONTEXT\n\n"
                context += "\n\n".join(f"## {c.source}: {c.section}\n{c.content}" for c in chunks)
        
        prompt = f"""## Target Artifact
File: {path.name}

```
{artifact}
```

## Your Mission
Perform a comprehensive security and failure analysis.
"""
        
        report = self.llm_client.generate(
            agent_config=redteam,
            user_prompt=prompt,
            context=context,
        )
        
        if output_file:
            output_path = self.redteam_path / output_file
            with open(output_path, "w") as f:
                f.write(f"# Red Team Report: {path.name}\n\n")
                f.write(f"Generated: {datetime.now().isoformat()}\n\n---\n\n")
                f.write(report)
            print(f"📄 Report saved to: {output_path}")
        
        return report
    
    def qa_artifact(self, artifact_path: str, output_file: Optional[str] = None,
                    contract: str = None, criteria: list[str] = None) -> str:
        """Run QA verification on any artifact file."""
        if AgentType.QA not in self.agents:
            raise ValueError("No QA agent configured.")
        
        path = Path(artifact_path)
        if not path.is_absolute():
            for folder in [self.artifacts_path, self.done_path, self.base_path]:
                if (folder / artifact_path).exists():
                    path = folder / artifact_path
                    break
        
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {artifact_path}")
        
        with open(path) as f:
            artifact = f.read()
        
        qa = self.agents[AgentType.QA]
        
        # Get relevant context
        context = None
        if self.context_retriever:
            chunks = self.context_retriever.retrieve(artifact[:1000], max_chunks=5)
            if chunks:
                context = "# RELEVANT DESIGN CONTEXT\n\n"
                context += "\n\n".join(f"## {c.source}: {c.section}\n{c.content}" for c in chunks)
        
        criteria_text = "\n".join(f"- {c}" for c in criteria) if criteria else "Not specified"
        
        prompt = f"""## Output Contract
{contract or "Not specified"}

## Acceptance Criteria
{criteria_text}

## Implementation to Verify
```
{artifact}
```

## Your Mission
Verify this implementation. Generate test cases. Identify issues.
"""
        
        report = self.llm_client.generate(
            agent_config=qa,
            user_prompt=prompt,
            context=context,
        )
        
        if output_file:
            output_path = self.qa_path / output_file
            with open(output_path, "w") as f:
                f.write(f"# QA Report: {path.name}\n\n")
                f.write(f"Generated: {datetime.now().isoformat()}\n\n---\n\n")
                f.write(report)
            print(f"📄 Report saved to: {output_path}")
        
        return report
