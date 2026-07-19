"""Execution-only OpenAI Responses API transport adapter.

This module transmits the exact request bytes already bound by an SFA-Bench
execution authorization. It does not construct prompts, retry automatically,
judge outputs, ratify evidence, or mutate benchmark policy.
"""
from __future__ import annotations

import json
import os
import socket
from typing import Any,