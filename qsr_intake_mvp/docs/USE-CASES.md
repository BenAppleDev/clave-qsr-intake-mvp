# Use Cases

## Internal Dashboard

A small operations or finance team can use the normalized outputs to power daily dashboards across orders, labor, and inventory without stitching together several incompatible export formats by hand.

## AI Assistant Grounded In Operational Data

An internal assistant can answer questions like “What happened at store X yesterday?” more safely when it is grounded in canonical records and metadata that expose confidence, freshness, and unresolved records.

## Workflow Automation

The pipeline can feed lightweight automations such as:

- flagging missing daily store data
- routing manual review when item mapping confidence drops
- triggering follow-up tasks when a source stops arriving on time

## Missing-Data And Anomaly Review

Because the system keeps raw truth and review states, it supports workflows where a human investigates:

- unmatched item names
- unexpected store naming drift
- missing labor or inventory extracts
- suspicious derived metrics that need source-level verification

## Public-Interest Or Nonprofit Deployment

A nonprofit network, food program, or mission-driven operator may have uneven software environments across sites. Some locations might expose structured exports while others rely on fragile back-office files. The Aloha integration and local-bridge split shows how to design one shared downstream pipeline even when field collection conditions differ.
