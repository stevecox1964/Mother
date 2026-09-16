# Mother architecture review

Project: **Mother — Main project**  
Source: `MOTHER_KNOWLEDGE_MODEL_ARCHITECTURE.md`  
Reviewed: September 10, 2026

This document concerns development of Mother itself. It is maintained in Mother's repository and selected as context only in the built-in Mother project. Ordinary projects retain their own configurations, conversations, and selected context.

## Assessment

The architecture separates reasoning, knowledge, execution, communication, and model building. Its strongest practical direction is to keep durable project knowledge outside the frontier model's working context, retrieve evidence when needed, and retain decisions and outcomes as structured experience. The proposed KR interface can begin with retrieval; trained project models can later implement the same interface.

The design is a roadmap, not a description of all current capabilities. Section 32 explicitly calls for incremental development. Section 33 should be adapted to the working app rather than treated as a reason to rebuild its existing components.

## Current implementation and gaps

- **Projects:** Independent configuration, conversations, selected files, search and Trash now exist, including a dedicated Mother development project. Structured requirements, decisions, tasks and project artifacts remain to be built.
- **Models:** Provider profiles, souls, expertise and file assignments exist. Registry identities still need separation from project bindings, with enforced role and capability permissions.
- **Broadcast:** Knowledge offers, evidence excerpts, selected speaker, useful additions, squelch and cancellation work today. Typed bus messages and explicit convergence packets retaining dissent remain.
- **Knowledge:** Selected source files and searchable saved messages exist. Project-KR, durable evidence records, cross-conversation retrieval, contradiction and staleness handling remain.
- **Execution:** Tools can read model settings and provider catalogs. Bounded workers, patch/test results, tool permissions and an apply/restart workflow remain.
- **Experience and learning:** Conversation events, configuration snapshots and run metadata are recorded. Curated outcomes, evaluation records, datasets, lineage, training and promotion remain.

## Recommended implementation sequence

1. Define a versioned internal message envelope with project ID, conversation ID, run ID, producer, purpose, source references and status. Introduce enforced capabilities while preserving the existing direct and broadcast modes.
2. Build a project-scoped knowledge and experience store. Record claims, evidence, source file hashes, decisions, corrections and outcomes. Use explicit tentative, supported, disputed and stale states. Model agreement or a confidence score alone must not promote a claim to fact.
3. Add a bounded retrieval-backed Project-KR and Knowledge Bus. Retrieve relevant records for new conversations in the same project; retain provenance and source visibility rules. Test project isolation and stale evidence before automatic reuse.
4. Add convergence packets without discarding dissent. Distinguish evidence-backed conclusions, recommendations and unresolved alternatives. Keep the current ability to stop or squelch participation.
5. Add the Tool Bus and bounded coding workers. For Mother updates, produce a patch, run tests in an isolated checkout, review the result, and apply changes with restart and rollback support. Being the main project must not itself grant a model unrestricted filesystem or process access.
6. Build training-candidate curation and evaluations from explicit rationale summaries, corrections and measured outcomes. Add dataset versions, model lineage and promotion criteria before training, adapter loading or automatic model promotion.

## Decisions to settle during implementation

- Which roles may request tools, publish user-facing messages, or promote knowledge? Enforce this in dispatch and publication code, not only in souls.
- What validates a finding, and what invalidates it when a file or assumption changes? Preserve contrary evidence and the history of corrections.
- What are the call, token, time and context budgets for KNOW, DO and CONCUR? Cancellation must cross bus boundaries and late output must remain discardable.
- Which project records can be reused by another project? Default to explicit references or promotion rather than merging project memories.
- Which held-out evaluations demonstrate that a trained model improves on retrieval and its base model? Avoid evaluating on the records used to train it.

The next useful milestone is a project-scoped knowledge store with evidence and retrieval. The Mother project supplies a concrete first case: this architecture, implementation decisions, tests and subsequent corrections can become its own maintained project knowledge.
