# Live Provider Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable real OpenAI-compatible provider use from CLI and Web UI without leaking credentials.

**Architecture:** Keep the existing `LLMProvider` interface. Improve `OpenAICompatibleProvider` output protocol prompting and normalization, then add Web form plumbing that chooses mock or live provider per request.

**Tech Stack:** Python 3.11, FastAPI, Jinja2, Typer, pytest, httpx.

## Tasks

### Task 1: Provider Protocol

- [ ] Add failing tests for system prompt payload and fenced JSON cleanup.
- [ ] Implement provider protocol messages and response normalization.
- [ ] Run provider tests.

### Task 2: Web Live Mode

- [ ] Add failing Web tests for live provider construction, missing key handling, and keyring save.
- [ ] Implement Web form fields and live/mock provider selection.
- [ ] Run Web tests.

### Task 3: Verification And Records

- [ ] Update process log with the post-review change.
- [ ] Run full pytest, compileall, and diff check.
- [ ] Commit the feature.
