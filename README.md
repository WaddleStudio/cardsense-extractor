# CardSense Extractor

Data extraction and normalization pipeline for CardSense.

This service converts raw credit card promotion text into
validated, versioned, normalized promotion records.

## What this repo does
- Ingests raw promotion text
- Extracts and normalizes promotion rules
- Validates data against shared contracts
- Writes normalized records to PostgreSQL

## What this repo does NOT do
- No recommendation logic
- No user-specific state
- No external synchronous API

## Related Repositories
- cardsense-contracts — Shared schemas and taxonomies
- cardsense-api — External decision API
