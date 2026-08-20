-- Create the local MySQL database for the NFL fantasy advisor project.
CREATE DATABASE IF NOT EXISTS nfl_fantasy_advisor
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

-- Make the project database active for the rest of this script.
USE nfl_fantasy_advisor;

-- Validation control: this should return nfl_fantasy_advisor.
SELECT DATABASE() AS active_database;