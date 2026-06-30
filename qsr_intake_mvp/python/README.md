# Python workers

Install deps:

```bash
python -m pip install -r requirements.txt
```

Run the local demo:

```bash
PYTHONPATH=python python -m qsr_intake.pipeline.run_demo
```

Run the Aloha scenarios:

```bash
PYTHONPATH=python python -m qsr_intake.pipeline.run_demo --scenario aloha_plan_a
PYTHONPATH=python python -m qsr_intake.pipeline.run_demo --scenario aloha_plan_b
```

Resolver configs live in:

- `sample_data/configs/canonical_item_catalog.yml`
- `sample_data/configs/normalization_resolver.yml`
