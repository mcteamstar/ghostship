# Spec Delta

## ADDED Requirements

### Requirement: Raven honors explicit model choices for delegated tasks
When Raven is instructed to dispatch a named persona task using a specific model, Raven SHALL pass that model through `ghostship-spawn` using its `--model` option.

#### Scenario: Standing order requests a model for delegated work
- **WHEN** Raven is instructed to start a named persona task using `claude-opus-5`
- **THEN** Raven dispatches through `ghostship-spawn <persona> --model claude-opus-5`
