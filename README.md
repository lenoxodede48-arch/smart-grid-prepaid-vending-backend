### High-Performance IoT Smart Grid Vending & Telemetry Engine

An enterprise-ready, asynchronous backend engine built to manage automatic utility credit (token) allocation and bidirectional telemetry updates for physical (single-phase) smart prepaid electric utility meters. The architecture handles real-time web checkouts, enforces strict transactional concurrency checks, and establishes low-overhead communication loops with hardware modules over the air.

## 🏛️ Core System Architecture
The framework decouples application responsibilities across three processing nodes communicating over secure internal network pathways:

```text
┌─────────────────────────────────┐
│     Frontend UI Website         │
└────────────────┬────────────────┘
                 │
             HTTP POST (Port 8000)
                 │
                 ▼
┌─────────────────────────────────┐                 📡 MQTT Port 1883           ┌────────────────────────────┐
│      FastAPI Vending Engine     ├────────────────────────────────────────────►│   Physical ESP32 Meter     │
└────────────────┬────────────────┘                                             └─────────────┬──────────────┘
                 │                                                                            │
      Asynchronous Pool Access                                                        Real-Time Telemetry
                 │                                                                            │
                 ▼                                                                            ▼
┌─────────────────────────────────┐                                             ┌────────────────────────────┐
│   PostgreSQL Database Cluster   │◄────────────────────────────────────────────┤    HiveMQ Public Broker    │
└─────────────────────────────────┘           Asynchronous Worker Loop          └────────────────────────────┘
```

## 🚀 Key Technical Highlights
* **Bulletproof Database Concurrency & Ledger Integrity:** Deployed a strict database transactional checking mechanism using `asyncpg` within isolated transaction blocks. Leveraged `UNIQUE` constraint parameters on payment indexes to eliminate duplicate generation loops (double-spending), returning an `HTTP 409 Conflict` status immediately if an edge-case transaction retry hits the pipeline.
* **Optimized Local Environment Tuning:** Tuned system-level authentication parameters (`pg_hba.conf`) on native Linux environments to authorize network loops safely using internal `trust` flags over loopback paths (`127.0.0.1`). Bypassed traditional password decoding issues, dropping internal lookup speeds down to sub-milliseconds.
* **High-Throughput Bidirectional IoT Gateway:** Implemented a persistent asynchronous driver connection pool to keep standard data channels open. The server intercepts streaming hardware updates over native MQTT TCP loops (`Port 1883`), dynamically isolates routing identifiers using single-level wildcard configurations (`tritech/readings/+`), and updates table metric states concurrently.

## 💾 Relational Database Schema Schema
The platform dynamically coordinates streaming parameters across three related storage modules:
* `users`: Stores customer accounts and manages relation mappings to system authorization identifiers.
* `meters`: The live asset registry inventory tracking physical devices and real-time credit consumption parameters (`current_balance_kwh`).
* `transactions`: An immutable financial audit trail ledger logging receipt inputs, subscription package choices, and unique generated 20-digit prepaid utility token keys.

## 🛠️ Production Stack & Dependencies
* **Core Application Framework:** FastAPI (Python)
* **Storage Infrastructure Engine:** PostgreSQL Relational Database Subsystem
* **Driver Pool Interconnection:** `asyncpg` Async DB Driver Wrapper
* **IoT Field Communication Protocol:** MQTT Protocol (HiveMQ Engine Cluster / `gmqtt`)
* **Validation & Schema Management:** Pydantic Models & Schemas
