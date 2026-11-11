# How to Reproduce

## Generate the governed learning evidence chain

```cmd
.venv\Scripts\python.exe -m amba_ai.cli.generate_governed_learning_evidence --project-root . --event-file submission\artifacts\governed_learning_events_input.json --source-inventory workstream13_current_sources.txt
```

Run the final targeted matrix:

```cmd
call verify_workstream13.cmd
```

Then run the complete regression:

```cmd
.venv\Scripts\python.exe -m pytest -q
```
