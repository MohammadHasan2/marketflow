# MarketFlow

Containerized Financial Data Orchestration Pipeline

## Overview

MarketFlow is an end-to-end data engineering project that ingests
daily financial market data, validates and transforms records,
loads them into PostgreSQL, and exposes the results through a
React dashboard.

## Architecture

Financial Market API
-> Apache Airflow running with Docker Compose
-> Python extraction, validation, and transformation
-> Supabase PostgreSQL
-> React + TypeScript dashboard
-> Cloudflare Pages

GitHub Actions runs automated tests and code-quality checks.

## Planned Features

- Daily financial data ingestion
- Configurable instrument symbols
- Data validation and quality checks
- Idempotent PostgreSQL upserts
- Airflow retries, scheduling, and task logs
- Pipeline execution auditing
- Automated tests and continuous integration
- Public dashboard for historical prices and pipeline health

## Local Development

The Airflow environment will run locally using Docker Compose.
See the setup instructions added during implementation.

## Configuration

Copy `.env.example` to `.env` and configure your credentials.
Never commit `.env` or expose database passwords in frontend code.

## Project Status

Under development.
