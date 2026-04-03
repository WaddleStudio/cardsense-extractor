-- Migration: Add subcategory column to promotion tables
-- Safe to run on existing databases — DEFAULT 'GENERAL' ensures backward compatibility.

ALTER TABLE promotion_versions ADD COLUMN subcategory TEXT NOT NULL DEFAULT 'GENERAL';
ALTER TABLE promotion_current ADD COLUMN subcategory TEXT NOT NULL DEFAULT 'GENERAL';
