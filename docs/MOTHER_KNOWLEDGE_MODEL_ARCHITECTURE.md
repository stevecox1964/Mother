# Mother Architecture
## Knowledge Bus, Tool Bus, Broadcast/Convergence, and Evolving Model Lifecycle

**Status:** Architectural design note  
**Project:** Mother  
**Purpose:** Define Mother as a multi-model cognitive harness that separates reasoning, knowledge, execution, research, communication, and long-term model evolution.

---

# 1. Vision

Mother is not a collection of chatbots talking to one another.

Mother is a **multi-model cognitive operating system**.

A small number of high-capability models act as architects, planners, reviewers, and communicators. Lower-cost and specialized models act as knowledge reservoirs, coding workers, researchers, and execution specialists.

The system should allow a project to accumulate knowledge over time and eventually **turn that accumulated project experience into models of its own**.

The long-term goal is therefore not only:

```text
Use models to build projects
```

but also:

```text
Projects produce knowledge
Knowledge produces training data
Training data produces models
Models become reusable project components
Those models help build future versions of the project
```

Mother should evolve.

---

# 2. Fundamental Separation of Responsibilities

Mother treats the following as separate capabilities:

```text
REASONING
    What should we think about?

KNOWLEDGE
    What is known?

ACTION
    What can perform the work?

COMMUNICATION
    What should the user see?

MEMORY
    What should survive beyond the current context?

MODEL BUILDING
    What accumulated knowledge is valuable enough
    to become learned model capability?
```

Modern LLM systems often combine all of these responsibilities inside one large model and one large context window.

Mother deliberately separates them.

---

# 3. High-Level Architecture

```text
                               USER
                                |
                                v
                     +----------------------+
                     |    COMMUNICATORS     |
                     |   Frontier Models    |
                     |   User-facing only   |
                     +----------+-----------+
                                |
                         intent / reasoning
                                |
                                v
              +--------------------------------------+
              |                MOTHER                |
              |                                      |
              | project state                        |
              | conversation state                   |
              | routing                              |
              | model lifecycle                      |
              | context management                   |
              | scheduling                           |
              | permissions                          |
              | broadcast / convergence              |
              | knowledge indexing                   |
              | training-data generation             |
              +----------+-------------+-------------+
                         |             |
                 KNOWLEDGE BUS       TOOL BUS
                         |             |
          +--------------+---+         +-------------------+
          |              |             |                   |
          v              v             v                   v
      Unreal KR       Project KR   Code Model          Unreal MCP
      C++ KR          Web KR       Test Model          Shell
      Robotics KR     Docs KR      Refactor Model      Git
      Domain KR       Repo KR      Build Model         Browser/APIs
```

Across the system sits another first-class mechanism:

```text
                          BROADCAST BUS
                               |
             +-----------------+------------------+
             |                 |                  |
             v                 v                  v
        Architect A       Architect B       Knowledge KRs
             |                 |                  |
             +-----------------+------------------+
                               |
                               v
                       CONVERGENCE LAYER
                               |
                               v
                         COMMUNICATOR
                               |
                               v
                              USER
```

Mother's three primary runtime primitives are:

```text
KNOW
    Query knowledge.

DO
    Perform work.

CONCUR
    Ask multiple intelligences independently,
    gather responses, and converge.
```

A fourth long-term primitive is:

```text
LEARN
    Convert accumulated project experience
    into reusable learned capability.
```

---

# 4. Project / Conversation / Model Architecture

The core hierarchy remains:

```text
Project
    -> Conversations
        -> Models
```

But the project should become a complete evolving knowledge environment:

```text
MOTHER
|
+-- Projects
|   |
|   +-- Project State
|   +-- Conversations
|   +-- Requirements
|   +-- Decisions
|   +-- Tasks
|   +-- Workflows
|   +-- Artifacts
|   +-- Research
|   +-- Execution History
|   +-- Knowledge Reservoirs
|   +-- Project Models
|   +-- Training Corpora
|   +-- Evaluations
|   +-- Model Lineage
|   +-- Tool Permissions
|
+-- Model Registry
+-- Knowledge Registry
+-- Tool Registry
+-- Prompt / Role Registry
+-- Message Bus
+-- Broadcast Bus
+-- Convergence Engine
+-- Context Manager
+-- Scheduler
+-- Model Builder
+-- Model Loader
+-- Evaluation System
+-- Audit / Trace Store
```

Projects therefore do not merely contain conversations.

They accumulate **machine-learnable experience**.

---

# 5. Model Roles

Roles should be enforced by Mother as capabilities and permissions, not merely described in prompts.

## 5.1 Communicator

The Communicator is the user-facing model.

Responsibilities:

- understand user intent,
- maintain conversational continuity,
- present decisions and results,
- surface important uncertainty,
- ask the user questions when needed,
- receive convergence results,
- keep internal multi-model traffic out of the user-facing conversation.

Only models with a capability such as:

```text
communicate:user
```

should be allowed to produce final user-visible messages.

---

## 5.2 Architect

Architects are high-capability reasoning models.

Responsibilities:

- analyze requirements,
- design systems,
- decompose projects,
- identify uncertainty,
- query Knowledge Reservoirs,
- request research,
- assign implementation work,
- inspect results,
- challenge assumptions,
- review designs,
- participate in convergence,
- propose decisions.

Multiple frontier models may serve as Architects.

This gives Mother multiple independent high-level perspectives rather than relying on a single model family.

---

## 5.3 Knowledge Reservoir

A Knowledge Reservoir, or KR, is **not an agent**.

A KR has:

- no independent goal,
- no project authority,
- no user-facing personality,
- no need to plan,
- no reason to initiate work,
- no reason to speak directly to the user.

Its role is:

```text
KnowledgeQuery
      |
      v
 Knowledge Reservoir
      |
      v
 KnowledgePacket
```

A KR is a vessel of knowledge.

It may internally be implemented using:

- a domain-trained model,
- continued pretraining,
- LoRA,
- merged LoRA weights,
- long-context models,
- RAG,
- vector databases,
- graph databases,
- SQL,
- code indexes,
- documentation indexes,
- APIs,
- web search,
- or combinations of these.

The caller should not care how the KR stores or produces knowledge.

---

## 5.4 Worker Model

Worker models perform bounded tasks.

Examples:

```text
Code Model
Test Model
Refactor Model
Build Model
Data Transformation Model
Asset Generation Model
Log Analysis Model
```

Workers receive structured work requests and return structured work products.

Example:

```text
WorkRequest
    |
    v
Coding Model
    |
    +-- patch
    +-- changed files
    +-- tests
    +-- compiler output
    +-- unresolved issues
```

A worker does not automatically become an Architect merely because it is capable of reasoning.

---

## 5.5 Research KR

Web searchers, scrapers, documentation readers, repository researchers, and similar systems should generally be treated as **knowledge producers**, not conversational agents.

They return:

- facts,
- excerpts,
- sources,
- URLs,
- timestamps,
- evidence,
- contradictions,
- confidence,
- uncertainty.

They answer questions for Mother.

They do not answer the end user directly.

---

# 6. Knowledge Bus

The Knowledge Bus provides a common interface for requesting knowledge.

An Architect should be able to ask:

```text
"What do we know about this?"
```

without needing to know whether the answer comes from:

```text
Project-KR
Unreal-KR
C++-KR
Documentation-KR
Web-KR
Repository-KR
A trained project model
A vector database
A long-context model
```

The physical implementation is hidden behind the bus.

## Targeted Query

```text
Architect
    |
    | query: unreal.navigation
    v
Unreal-KR
    |
    v
KnowledgePacket
```

## Routed Query

```text
Architect
    |
    v
Knowledge Bus
    |
    +--> Unreal-KR
    +--> Project-KR
    +--> C++-KR
    +--> Documentation-KR
    |
    v
rank / merge
    |
    v
KnowledgePacket
```

## Knowledge Broadcast

When the Architect does not know who has the answer:

```text
"Who knows something relevant about this?"
```

Mother can fan the query out.

Example:

```text
Unreal-KR       relevance 0.97
Project-KR      relevance 0.91
C++-KR          relevance 0.75
Physics-KR      relevance 0.48
Automotive-KR   relevance 0.01
```

Only relevant responses need to move upward.

---

# 7. Knowledge Packets

KRs should return structured knowledge rather than chatbot prose.

Example:

```json
{
  "type": "knowledge_packet",
  "query_id": "kq_00192",
  "domain": "unreal.navigation",
  "facts": [
    {
      "statement": "Short navigation segments can reduce long-horizon deviation.",
      "confidence": 0.92
    }
  ],
  "relationships": [
    {
      "subject": "short-hop navigation",
      "relation": "reduces",
      "object": "long-horizon path deviation"
    }
  ],
  "evidence": [],
  "sources": [],
  "conflicts": [],
  "unknowns": [
    "Behavior may depend on project navigation settings."
  ],
  "confidence": 0.88
}
```

The schema can evolve, but Mother should preserve concepts such as:

```text
facts
relationships
evidence
provenance
confidence
uncertainty
conflicts
relevance
```

The KR supplies knowledge.

The Architect interprets it.

---

# 8. Tool Bus

The Tool Bus is separate from the Knowledge Bus.

The distinction is:

```text
KNOWLEDGE BUS

"What do I need to know?"
```

versus:

```text
TOOL BUS

"What needs to be done?"
```

Examples of Tool Bus endpoints:

```text
Unreal MCP
Shell
Compiler
Test Runner
Git
File System
Database
Browser
Build System
Deployment
Image Generation
Video Generation
External APIs
```

A typical workflow may look like:

```text
1. KNOW
   Ask Project-KR for current architecture.

2. KNOW
   Ask Unreal-KR for relevant engine behavior.

3. CONCUR
   Ask two Architects to independently evaluate options.

4. DO
   Send implementation request to Coding Model.

5. DO
   Compile and run tests.

6. KNOW
   Ask diagnostic KR to interpret failures.

7. DO
   Send repair request to Coding Model.

8. CONCUR
   Have Architects review the completed change.

9. COMMUNICATE
   Tell the user what happened.
```

---

# 9. Broadcast Bus

Broadcast is a first-class Mother capability.

One question can be sent to many participants.

```text
                         QUESTION
                            |
                            v
                      BROADCAST BUS
                            |
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
    Architect A         Architect B          KR Group
        |                   |                   |
        +-------------------+-------------------+
                            |
                            v
                        RESPONSES
                            |
                            v
                    CONVERGENCE ENGINE
```

Broadcast can support several scopes.

## Explicit Broadcast

```text
targets:
    - architect.frontier_a
    - architect.frontier_b
    - kr.unreal
```

## Capability Broadcast

```text
capabilities:
    - software_architecture
    - unreal_engine
```

## Project Broadcast

```text
scope: project
```

## Knowledge-Only Broadcast

```text
scope: knowledge
```

Broadcast allows many models to contribute without turning the project into a giant multi-agent chat room.

---

# 10. Convergence

Broadcast without convergence creates noise.

Mother therefore needs a Convergence Layer.

Example input:

```text
Architect A:
    Prefer approach X.

Architect B:
    Prefer approach Y.

Unreal-KR:
    X has known failure condition Z.

Project-KR:
    Y conflicts with project decision D-104.

Test-KR:
    Existing tests currently support X.
```

Mother produces something closer to:

```json
{
  "type": "convergence_packet",
  "consensus": [
    "The current implementation should be replaced."
  ],
  "recommended_direction": "Approach X",
  "support": [
    "Compatible with project decision D-104.",
    "Supported by existing tests."
  ],
  "dissent": [
    {
      "source": "Architect B",
      "concern": "Approach X has failure condition Z."
    }
  ],
  "required_followup": [
    "Mitigate failure condition Z."
  ]
}
```

The Communicator receives the convergence result.

It does not need every intermediate internal message.

This allows:

```text
30 participating models
thousands of internal messages
many research operations
many tool calls
```

to collapse into:

```text
one coherent user-facing answer
```

---

# 11. Context Management

A major Mother objective is preventing frontier-model context from becoming a warehouse.

The undesirable pattern is:

```text
Frontier Model Context
    + conversation history
    + source code
    + documentation
    + web research
    + logs
    + requirements
    + old decisions
    + test results
    + tool output
    + previous summaries
    + more code
```

Mother should move toward:

```text
                  FRONTIER MODEL
                         |
                  Working Context
                         |
                  "I need X"
                         |
                         v
                   Knowledge Bus
                         |
             +-----------+-----------+
             |           |           |
             v           v           v
           KR-A         KR-B         KR-C
             |           |           |
             +-----------+-----------+
                         |
                         v
                 Knowledge Packet
                         |
                         v
                     Reasoning
```

The frontier model's context becomes:

```text
WORKING MEMORY
```

rather than:

```text
LONG-TERM STORAGE
```

---

# 12. Project Knowledge Reservoir

Every substantial Mother project should eventually have a Project-KR.

The Project-KR represents accumulated project knowledge.

Potential contents include:

```text
requirements
architecture
decisions
rejected approaches
implementation history
source-code understanding
component relationships
known bugs
tests
build behavior
deployment behavior
user-approved conventions
research findings
external documentation
important conversation outcomes
```

The Project-KR is not simply conversation history.

It is the project's accumulated usable knowledge.

---

# 13. The Model-Building Workflow

Model building is a core part of Mother's long-term architecture.

A project should be capable of generating models from the knowledge created while the project is being built.

The workflow is:

```text
PROJECT ACTIVITY
     |
     +-- conversations
     +-- architecture decisions
     +-- implementation work
     +-- code changes
     +-- research
     +-- reviews
     +-- failures
     +-- corrections
     +-- tests
     +-- successful solutions
     +-- model critiques
     +-- reasoning summaries
     |
     v
EXPERIENCE STORE
     |
     v
CURATION / DISTILLATION
     |
     v
TRAINING CORPUS
     |
     v
MODEL BUILD
     |
     v
EVALUATION
     |
     v
PROJECT MODEL / KR
     |
     v
MODEL REGISTRY
```

The result becomes another loadable resource available to Mother.

---

# 14. Conversations Become Training Material

Conversations should not be regarded only as chat transcripts.

They are raw project experience.

A useful conversation may contain:

```text
problem definitions
requirements
architectural proposals
alternatives considered
questions
research findings
user corrections
accepted decisions
rejected decisions
implementation instructions
code-review results
failure diagnoses
successful fixes
```

Mother should be able to transform selected conversations into structured training records.

For example:

```json
{
  "type": "architecture_training_record",
  "project": "unreal-sim",
  "problem": "...",
  "context": "...",
  "constraints": ["...", "..."],
  "knowledge_used": ["...", "..."],
  "alternatives": ["...", "..."],
  "decision": "...",
  "rationale_summary": "...",
  "result": "...",
  "evaluation": {
    "successful": true
  }
}
```

The system should favor explicit reasoning summaries, decisions, critiques, evidence, and outcomes rather than depending on raw hidden chain-of-thought.

The valuable artifact is not every token a model generated.

The valuable artifact is the **learned project experience**.

---

# 15. Experience Store

Mother should maintain a structured Experience Store separate from ordinary chat history.

Possible record types:

```text
ConversationOutcome
ArchitectureDecision
KnowledgePacket
ConvergencePacket
WorkRequest
WorkResult
CodePatch
TestResult
FailureRecord
RepairRecord
ResearchRecord
UserCorrection
AcceptedSolution
RejectedSolution
EvaluationRecord
ModelPerformanceRecord
```

These become candidates for:

```text
retrieval
project memory
evaluation
training data
distillation
future KR construction
```

---

# 16. Model Factory

Mother should eventually contain a Model Factory.

The Model Factory turns accumulated project experience into learned capability.

Conceptually:

```text
                     PROJECT EXPERIENCE
                            |
                            v
                      Dataset Builder
                            |
                    +-------+-------+
                    |               |
                    v               v
              Positive Data     Negative Data
                    |               |
                    +-------+-------+
                            |
                            v
                         Trainer
                            |
          +-----------------+------------------+
          |                 |                  |
          v                 v                  v
        LoRA        Continued Pretraining    Distillation
          |                 |                  |
          +-----------------+------------------+
                            |
                            v
                        Candidate Model
                            |
                            v
                        Evaluation
                            |
                     pass / reject
                            |
                            v
                        Model Registry
```

Mother should support multiple learning strategies:

```text
LoRA
QLoRA
continued pretraining
domain-adaptive pretraining
supervised fine-tuning
preference tuning
distillation
adapter merging
future model-expansion techniques
```

The architecture should not hard-code Mother to one training method.

---

# 17. Models as Project Artifacts

A trained model should become a first-class project artifact.

Example:

```text
Project: Unreal SIM

Models:
    unreal-project-kr-v1
    unreal-navigation-kr-v2
    unreal-cpp-worker-v1
    unreal-architecture-student-v3
```

Each model should have metadata such as:

```text
model_id
project_id
base_model
role
capabilities
training_dataset
training_method
training_date
version
evaluation_scores
hardware_requirements
context_window
memory_requirements
lineage
dependencies
status
```

---

# 18. Model Lineage

Mother must know where a model came from.

Example:

```text
Qwen Base
   |
   +-- Unreal Domain CPT
          |
          +-- Unreal-KR-v1
                 |
                 +-- Project Conversations
                 +-- Project Decisions
                 +-- Code History
                 |
                 +-- Unreal-SIM-KR-v2
                        |
                        +-- Navigation Experience
                        |
                        +-- Unreal-SIM-KR-v3
```

Model lineage allows Mother to answer:

```text
What data created this model?

Which project did it come from?

What changed between v2 and v3?

Which base model was used?

Which LoRAs were merged?

What evaluations did it pass?

Should this model still be trusted?
```

---

# 19. Dynamic Model Loading

Models do not need to remain loaded permanently.

Mother should treat models as loadable cognitive resources.

Example:

```text
Mother receives task
        |
        v
Determine capabilities needed
        |
        v
Model Registry
        |
        +-- Unreal-KR
        +-- C++-KR
        +-- Project-KR
        |
        v
Load required models
        |
        v
Perform work
        |
        v
Unload when idle
```

This is especially important for local GPU systems.

A machine may possess many specialized models but only have enough VRAM to load one or two at a time.

Mother therefore needs a **Model Loader / Model Scheduler**.

Responsibilities:

```text
load model
unload model
activate LoRA
deactivate LoRA
swap model
cache hot models
track VRAM
track RAM
track inference backend
track model startup cost
route around unavailable models
```

---

# 20. Knowledge Reservoirs Can Evolve Into Models

A KR may begin life as ordinary retrieval.

Example:

```text
Unreal Documentation
       |
       v
Vector Database
       |
       v
Unreal-KR-v0
```

As the project generates experience:

```text
docs
+ project conversations
+ source code
+ solved problems
+ web research
+ architecture decisions
```

Mother can create:

```text
Unreal-KR-v1 LoRA
```

Later:

```text
Unreal-KR-v2 merged model
```

Later:

```text
Project-specific Unreal-SIM-KR
```

So knowledge can progressively move through stages:

```text
RAW INFORMATION

       v

RETRIEVABLE KNOWLEDGE

       v

CURATED KNOWLEDGE

       v

TRAINING DATA

       v

LEARNED KNOWLEDGE

       v

SPECIALIZED MODEL
```

This is a core evolutionary mechanism.

---

# 21. Models Can Become More Specialized Over Time

Mother should not assume that every project model remains general-purpose.

A model can intentionally become extremely narrow.

For example:

```text
Unreal-Navigation-KR
```

may be excellent at:

```text
NavMesh
AI MoveTo
path following
dynamic obstacles
navigation failure analysis
project-specific movement architecture
```

while being poor at:

```text
conversation
poetry
general history
marketing
unrelated programming
```

That is acceptable.

The model is a knowledge component, not an assistant.

---

# 22. Project-Specific Distillation

One especially important future workflow is distillation from high-level models into lower-level project models.

Example:

```text
Frontier Architects
        |
        +-- solve problems
        +-- review designs
        +-- inspect failures
        +-- make decisions
        |
        v
High-quality Experience Records
        |
        v
Distillation Dataset
        |
        v
Small Project Model
```

Over time:

```text
Frontier model does less routine project reasoning.

Project-specific model handles more known situations.

Frontier model is called for novelty, ambiguity,
architecture, or high-risk decisions.
```

This creates a natural intelligence hierarchy.

---

# 23. Evolutionary Architecture

Mother should be designed so that a mature project becomes progressively more self-contained.

Early project:

```text
Frontier Models
      |
      +--> Web Search
      +--> Documentation
      +--> General Coding Models
```

Intermediate project:

```text
Frontier Models
      |
      +--> Project-KR
      +--> Domain-KRs
      +--> Project-aware Code Models
```

Mature project:

```text
Frontier Architects
      |
      +--> Highly specialized Project-KRs
      +--> Project-trained Workers
      +--> Project-specific evaluators
      |
      +--> Frontier models only when necessary
```

The project develops its own cognitive infrastructure.

---

# 24. The Self-Improving Project Loop

The desired long-term loop is:

```text
          USER / PROJECT GOAL
                  |
                  v
              MOTHER
                  |
         +--------+--------+
         |                 |
         v                 v
     Architects          KRs
         |                 |
         +--------+--------+
                  |
                  v
               Workers
                  |
                  v
               Results
                  |
                  v
            Evaluations
                  |
                  v
          Experience Store
                  |
                  v
            Dataset Builder
                  |
                  v
             Model Factory
                  |
                  v
             New Models
                  |
                  v
            Model Registry
                  |
                  v
                MOTHER
```

This closes the loop.

Mother uses models to create better project-specific models.

---

# 25. Example: Unreal SIM Evolution

An Unreal SIM project might begin with:

```text
GPT-class Architect
Second Frontier Architect
General Coding Model
WebSearch-KR
Unreal Documentation KR
```

After months of work, Mother may have accumulated:

```text
thousands of project conversations
architecture decisions
navigation experiments
code changes
compiler failures
test results
Unreal documentation
successful patterns
failed patterns
model critiques
project-specific terminology
```

Mother builds:

```text
Unreal-SIM-Project-KR-v1
```

Then:

```text
Unreal-SIM-Coding-LoRA-v1
```

Then perhaps:

```text
Unreal-SIM-Navigation-KR-v2
```

Future architecture work might look like:

```text
Frontier Architect:
    "How does navigation currently work?"

        |
        v

Unreal-SIM-Navigation-KR-v2

        |
        v

Project-specific knowledge immediately returned
without injecting months of project history
into the frontier model's context.
```

---

# 26. Knowledge Bus vs Tool Bus vs Model Bus

As the architecture matures, Mother effectively has three resource planes.

## Knowledge Plane

```text
KNOWLEDGE BUS
```

Answers:

```text
Who knows this?
```

## Action Plane

```text
TOOL BUS
```

Answers:

```text
Who or what can do this?
```

## Cognitive / Model Plane

```text
MODEL REGISTRY + MODEL LOADER
```

Answers:

```text
Which intelligence should be active for this task?
```

Broadcast and convergence operate across all three.

---

# 27. Design Principle: Models Are Replaceable

Every model should sit behind a role or capability interface.

Mother should avoid logic such as:

```text
if model == "some-provider-model":
```

and prefer:

```text
capability:
    architecture
    coding
    knowledge.unreal
    knowledge.project
    research.web
    communicate.user
```

Then models can be:

```text
added
removed
upgraded
fine-tuned
distilled
replaced
loaded
unloaded
```

without changing project logic.

---

# 28. Design Principle: Preserve Dissent

Convergence should not erase disagreement.

Mother should preserve:

```text
consensus
minority opinions
confidence
evidence
unknowns
failed alternatives
```

A disagreement may become valuable future training data.

For example:

```text
Architect A predicted X.
Architect B predicted Y.
Implementation proved Y correct.
```

That is a powerful training record.

---

# 29. Design Principle: Failures Are Training Data

Mother should save failures when they contain useful information.

Examples:

```text
bad architecture
compiler failures
incorrect assumptions
failed tool calls
bad navigation strategy
incorrect model recommendation
user correction
reverted code
test regression
```

The ideal training record contains both:

```text
what failed
```

and:

```text
what eventually worked
```

This is more valuable than recording only successes.

---

# 30. Design Principle: Model Thought Becomes Structured Experience

Model reasoning can contribute to future learning, but Mother should not depend on retaining unrestricted raw internal chain-of-thought.

Instead, important reasoning should be converted into explicit project artifacts such as:

```text
rationale summaries
decision records
architecture comparisons
critiques
assumptions
predictions
evidence used
confidence estimates
postmortems
```

These artifacts are:

```text
inspectable
trainable
searchable
versionable
auditable
```

and are better suited for long-term model building.

---

# 31. Suggested Core Message Types

Mother will eventually benefit from a common protocol.

Initial message types could include:

```text
UserMessage
ArchitectureRequest
KnowledgeQuery
KnowledgePacket
ResearchRequest
ResearchPacket
WorkRequest
WorkResult
ToolRequest
ToolResult
BroadcastRequest
BroadcastResponse
ConvergencePacket
DecisionRecord
EvaluationRequest
EvaluationResult
ExperienceRecord
TrainingCandidate
ModelBuildRequest
ModelBuildResult
ModelLoadRequest
ModelUnloadRequest
```

The protocol should remain model-provider independent.

---

# 32. Suggested Core Services

A future Mother architecture may contain:

```text
ProjectManager

ConversationManager

ContextManager

ModelRegistry

ModelLoader

KnowledgeRegistry

KnowledgeRouter

ToolRegistry

ToolRouter

BroadcastManager

ConvergenceEngine

ExperienceStore

DatasetBuilder

ModelFactory

EvaluationEngine

Scheduler

AuditStore
```

These should evolve incrementally rather than being built all at once.

---

# 33. Initial Development Priority

The architecture is broad, but implementation should remain incremental.

A reasonable order is:

```text
1. Model Registry

2. Role / Capability System

3. Structured Internal Messages

4. Knowledge Bus

5. Tool Bus

6. Broadcast

7. Convergence

8. Project-KR

9. Experience Store

10. Training Candidate Extraction

11. Model Registry support for local models and LoRAs

12. Dynamic model loading / unloading

13. Dataset Builder

14. Model Factory

15. Automated evaluation and promotion
```

The model-building system does not need to be complete before Mother becomes useful.

However, **the data architecture should be designed from the beginning so today's project activity can become tomorrow's training data.**

That is critical.

---

# 34. Long-Term End State

The long-term vision is:

```text
                          USER
                           |
                           v
                   COMMUNICATOR
                           |
                           v
                         MOTHER
                           |
       +-------------------+-------------------+
       |                   |                   |
       v                   v                   v
   ARCHITECTS         KNOWLEDGE BUS        TOOL BUS
       |                   |                   |
       |             +-----+------+       +----+------+
       |             |            |       |           |
       |             v            v       v           v
       |          Domain KR   Project KR  Code       Tools
       |                                     Models
       |
       +-------------------+
                           |
                           v
                      CONVERGENCE
                           |
                           v
                         RESULT
                           |
                           v
                    EXPERIENCE STORE
                           |
                           v
                     MODEL FACTORY
                           |
                           v
                      NEW MODELS
                           |
                           v
                     MODEL REGISTRY
                           |
                           +------> loaded when needed
```

Mother therefore becomes more than an orchestration harness.

It becomes an evolving ecosystem where:

```text
projects create experience,
experience becomes knowledge,
knowledge becomes training data,
training data becomes models,
models become new cognitive components,
and those components help the project continue evolving.
```

---

# 35. Core Principle

The architectural principle to protect as Mother grows is:

> **The strongest models should spend their intelligence on reasoning, architecture, judgment, and communication—not on carrying every piece of project knowledge in their context window.**

Knowledge can live elsewhere.

Execution can live elsewhere.

Research can live elsewhere.

Specialized learned capability can live elsewhere.

Mother brings the correct pieces together when they are needed.

And over time, Mother should be capable of **building those pieces itself**.
