# Contributing

## Before you commit

Run the publish gate locally — it's the same check CI runs, so a clean local
run means a clean PR:

```sh
./scripts/scan.sh
```

Wire it up as a local pre-commit hook so it runs automatically:

```sh
cat > .git/hooks/pre-commit <<'EOF'
#!/usr/bin/env bash
exec ./scripts/scan.sh --staged
EOF
chmod +x .git/hooks/pre-commit
```

## Editing the rule chain

`custom_templates/boiler_monitoring.jinja`'s `boiler_word()` macro is the
one place the five status rules live (see its own header, and
`docs/boiler-monitoring-logic.md`, for why it's a macro and not inline
template YAML). After any change, re-run its selftest — no running Home
Assistant required:

```sh
pip install jinja2 pyyaml   # if you don't already have them
python3 scripts/_jinja_selftest.py
```

It stubs HA's `states()`/`is_state()`/`now()` against a fake state table and
asserts each of the five rules fires in the documented order, including the
"fresh install, nothing has ever fired yet" edge case. Add a case there for
any new rule or threshold before changing the macro.

## Re-rendering the flowchart

`docs/boiler-monitoring-logic.mmd` is the editable Mermaid source;
`.svg`/`.png` are pre-rendered so GitHub (and anything else that doesn't run
Mermaid) shows it without truncating. Re-render after editing the `.mmd`:

```sh
mmdc -i docs/boiler-monitoring-logic.mmd -o docs/boiler-monitoring-logic.svg -b "#1e1e1e"
mmdc -i docs/boiler-monitoring-logic.mmd -o docs/boiler-monitoring-logic.png -b "#1e1e1e" --size 1600 -s 2
```

(`mmdc` is the [mermaid-cli](https://github.com/mermaid-js/mermaid-cli)
package. No local Chrome install needed if you use its Docker image:
`docker run --rm -v "$PWD":/data minlag/mermaid-cli ...`.)
