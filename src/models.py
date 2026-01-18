"""
Core data models for the agent workflow engine.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    REVIEW = "review"          # Waiting for human review
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"
    REWORK = "rework"          # Sent back for automated rework


class AgentType(Enum):
    # Core agents (always available)
    DEVELOPER = "developer"    # Generic developer - adapts to any domain
    REVIEWER = "reviewer"      # Code review with reflection
    PLANNER = "planner"        # Task decomposition
    CONTRACT = "contract"      # Interface definition
    REDTEAM = "redteam"        # Adversarial testing
    QA = "qa"                  # Quality assurance / verification
    TESTER = "tester"          # Test generation (legacy, use QA)
    
    @classmethod
    def _missing_(cls, value):
        """Allow dynamic agent types from config files."""
        obj = object.__new__(cls)
        obj._value_ = value
        obj._name_ = value.upper()
        return obj


class TaskType(Enum):
    """
    Task types enforce workflow ordering:
    - CONTRACT tasks define interfaces (must come first)
    - IMPLEMENTATION tasks build the code (depend on contracts)
    - TEST tasks verify behavior (depend on implementations)
    """
    CONTRACT = "contract"           # Defines interfaces, types, APIs
    IMPLEMENTATION = "implementation"  # Builds the actual code
    TEST = "test"                   # Verifies behavior
    DOCUMENTATION = "documentation" # Writes docs
    PLANNING = "planning"           # Decomposes features


@dataclass
class LoopConfig:
    """Configuration for the feedback loop (rework loop)."""
    enabled: bool = False
    max_iterations: int = 3        # Maximum rework attempts
    require_reviewer: bool = True   # Run reviewer in loop
    require_redteam: bool = False   # Run red team in loop
    require_qa: bool = True         # Run QA in loop
    
    # Thresholds for passing
    min_review_score: float = 0.7
    qa_must_pass: bool = True
    redteam_max_critical: int = 0   # Max critical issues allowed
    
    @classmethod
    def from_dict(cls, data: dict) -> "LoopConfig":
        if data is None:
            return cls()
        return cls(
            enabled=data.get("enabled", False),
            max_iterations=data.get("max_iterations", 3),
            require_reviewer=data.get("require_reviewer", True),
            require_redteam=data.get("require_redteam", False),
            require_qa=data.get("require_qa", True),
            min_review_score=data.get("min_review_score", 0.7),
            qa_must_pass=data.get("qa_must_pass", True),
            redteam_max_critical=data.get("redteam_max_critical", 0),
        )
    
    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "max_iterations": self.max_iterations,
            "require_reviewer": self.require_reviewer,
            "require_redteam": self.require_redteam,
            "require_qa": self.require_qa,
            "min_review_score": self.min_review_score,
            "qa_must_pass": self.qa_must_pass,
            "redteam_max_critical": self.redteam_max_critical,
        }


@dataclass
class LoopState:
    """Tracks the state of the feedback loop for a task."""
    iteration: int = 0
    review_scores: list[float] = field(default_factory=list)
    qa_results: list[str] = field(default_factory=list)  # PASS/FAIL/NEEDS_WORK
    redteam_critical_counts: list[int] = field(default_factory=list)
    feedback_history: list[str] = field(default_factory=list)
    
    def add_iteration(self, review_score: float = None, qa_result: str = None, 
                      redteam_critical: int = None, feedback: str = None):
        self.iteration += 1
        if review_score is not None:
            self.review_scores.append(review_score)
        if qa_result is not None:
            self.qa_results.append(qa_result)
        if redteam_critical is not None:
            self.redteam_critical_counts.append(redteam_critical)
        if feedback is not None:
            self.feedback_history.append(feedback)
    
    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "review_scores": self.review_scores,
            "qa_results": self.qa_results,
            "redteam_critical_counts": self.redteam_critical_counts,
            "feedback_history": self.feedback_history,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "LoopState":
        if data is None:
            return cls()
        return cls(
            iteration=data.get("iteration", 0),
            review_scores=data.get("review_scores", []),
            qa_results=data.get("qa_results", []),
            redteam_critical_counts=data.get("redteam_critical_counts", []),
            feedback_history=data.get("feedback_history", []),
        )


@dataclass
class AgentConfig:
    """Configuration for a specialized agent."""
    name: str
    agent_type: AgentType
    model: str
    system_prompt: str
    temperature: float = 0.7
    max_tokens: int = 4096
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentConfig":
        return cls(
            name=data["name"],
            agent_type=AgentType(data["agent_type"]),
            model=data["model"],
            system_prompt=data["system_prompt"],
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens", 4096),
        )


@dataclass
class Task:
    """A single task in the workflow."""
    id: str
    title: str
    description: str
    agent_type: AgentType
    prompt: str
    depends_on: list[str] = field(default_factory=list)
    requires_review: bool = True
    requires_human_approval: bool = True
    requires_redteam: bool = False
    requires_qa: bool = False
    status: TaskStatus = TaskStatus.PENDING
    artifact_path: Optional[str] = None
    review_feedback: Optional[str] = None
    redteam_report: Optional[str] = None
    qa_report: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    # Contract-driven task support
    input_contract: Optional[str] = None
    output_contract: Optional[str] = None
    acceptance_criteria: list[str] = field(default_factory=list)
    # Task type for workflow ordering
    task_type: TaskType = TaskType.IMPLEMENTATION
    # Link to contract task (for implementation tasks)
    contract_task: Optional[str] = None
    # Feedback loop configuration
    loop_config: LoopConfig = field(default_factory=LoopConfig)
    loop_state: LoopState = field(default_factory=LoopState)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        # Default task_type based on agent_type if not specified
        task_type_str = data.get("task_type")
        if task_type_str:
            task_type = TaskType(task_type_str)
        elif data.get("agent_type") == "contract":
            task_type = TaskType.CONTRACT
        elif data.get("agent_type") in ("tester", "qa"):
            task_type = TaskType.TEST
        elif data.get("agent_type") == "planner":
            task_type = TaskType.PLANNING
        else:
            task_type = TaskType.IMPLEMENTATION
        
        # Parse loop config
        loop_config = LoopConfig.from_dict(data.get("loop"))
        loop_state = LoopState.from_dict(data.get("loop_state"))
            
        return cls(
            id=data["id"],
            title=data["title"],
            description=data.get("description", ""),
            agent_type=AgentType(data["agent_type"]),
            prompt=data["prompt"],
            depends_on=data.get("depends_on", []),
            requires_review=data.get("requires_review", True),
            requires_human_approval=data.get("requires_human_approval", True),
            requires_redteam=data.get("requires_redteam", False),
            requires_qa=data.get("requires_qa", False),
            status=TaskStatus(data.get("status", "pending")),
            input_contract=data.get("input_contract"),
            output_contract=data.get("output_contract"),
            acceptance_criteria=data.get("acceptance_criteria", []),
            task_type=task_type,
            contract_task=data.get("contract_task"),
            loop_config=loop_config,
            loop_state=loop_state,
        )
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "agent_type": self.agent_type.value,
            "prompt": self.prompt,
            "depends_on": self.depends_on,
            "requires_review": self.requires_review,
            "requires_human_approval": self.requires_human_approval,
            "requires_redteam": self.requires_redteam,
            "requires_qa": self.requires_qa,
            "status": self.status.value,
            "artifact_path": self.artifact_path,
            "review_feedback": self.review_feedback,
            "redteam_report": self.redteam_report,
            "qa_report": self.qa_report,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "input_contract": self.input_contract,
            "output_contract": self.output_contract,
            "acceptance_criteria": self.acceptance_criteria,
            "task_type": self.task_type.value,
            "contract_task": self.contract_task,
            "loop": self.loop_config.to_dict(),
            "loop_state": self.loop_state.to_dict(),
        }


@dataclass
class ReviewResult:
    """Result from a review agent."""
    passed: bool
    score: float  # 0-1
    feedback: str
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class QAResult:
    """Result from QA verification."""
    status: str  # PASS, FAIL, NEEDS_WORK
    contract_compliance: dict = field(default_factory=dict)  # item -> MET/NOT_MET/PARTIAL
    criteria_results: dict = field(default_factory=dict)     # criterion -> PASS/FAIL
    edge_cases: list[dict] = field(default_factory=list)
    test_cases: str = ""
    issues: list[str] = field(default_factory=list)
    
    @property
    def passed(self) -> bool:
        return self.status == "PASS"


@dataclass
class RedTeamResult:
    """Result from red team analysis."""
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    report: str
    vulnerabilities: list[dict] = field(default_factory=list)
    
    @property
    def has_critical(self) -> bool:
        return self.critical_count > 0
    
    @property
    def total_issues(self) -> int:
        return self.critical_count + self.high_count + self.medium_count + self.low_count


@dataclass 
class WorkflowState:
    """Current state of the workflow."""
    tasks: dict[str, Task] = field(default_factory=dict)
    completed_tasks: list[str] = field(default_factory=list)
    current_task: Optional[str] = None
    
    def get_ready_tasks(self) -> list[Task]:
        """Get tasks whose dependencies are all completed."""
        ready = []
        for task_id, task in self.tasks.items():
            if task.status in (TaskStatus.PENDING, TaskStatus.REWORK):
                deps_met = all(
                    dep in self.completed_tasks 
                    for dep in task.depends_on
                )
                if deps_met:
                    ready.append(task)
        return ready
    
    def get_tasks_by_type(self, task_type: TaskType) -> list[Task]:
        """Get all tasks of a specific type."""
        return [t for t in self.tasks.values() if t.task_type == task_type]
    
    def get_tasks_in_loop(self) -> list[Task]:
        """Get tasks currently in the feedback loop."""
        return [t for t in self.tasks.values() 
                if t.loop_config.enabled and t.loop_state.iteration > 0 
                and t.status != TaskStatus.COMPLETED]
    
    def validate_workflow_order(self) -> list[str]:
        """
        Validate that workflow ordering is correct.
        Returns list of warnings.
        """
        warnings = []
        
        for task in self.tasks.values():
            if task.task_type == TaskType.IMPLEMENTATION:
                has_contract = (
                    task.input_contract is not None or
                    task.output_contract is not None or
                    task.contract_task is not None or
                    any(
                        self.tasks.get(dep) and 
                        self.tasks[dep].task_type == TaskType.CONTRACT
                        for dep in task.depends_on
                    )
                )
                
                if not has_contract:
                    warnings.append(
                        f"⚠️  {task.id}: Implementation task has no contracts defined. "
                        f"Consider adding input_contract/output_contract or depending on a contract task."
                    )
        
        return warnings
