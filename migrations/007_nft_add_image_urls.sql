-- Add token_image_url to on-chain event tables
-- Migration: 007_nft_add_image_urls.sql
-- Purpose: Store token images for mint, transfer, and burn events

ALTER TABLE nft_mints ADD COLUMN IF NOT EXISTS token_image_url TEXT;
ALTER TABLE nft_transfers ADD COLUMN IF NOT EXISTS token_image_url TEXT;
ALTER TABLE nft_burns ADD COLUMN IF NOT EXISTS token_image_url TEXT;
