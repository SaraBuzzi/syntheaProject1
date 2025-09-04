

CREATE SCHEMA IF NOT EXISTS owner;
CREATE SCHEMA IF NOT EXISTS server;

-- OWNER
DROP TABLE IF EXISTS owner.patients_owner CASCADE;
CREATE TABLE owner.patients_owner (
  id                  TEXT PRIMARY KEY,
  birthdate           DATE,
  ssn                 TEXT,
  drivers             TEXT,
  passport            TEXT,
  first               TEXT,
  middle              TEXT,
  last                TEXT,
  maiden              TEXT,
  address             TEXT,
  city                TEXT,
  fips                TEXT,
  zip                 TEXT,
  lat                 DOUBLE PRECISION,
  lon                 DOUBLE PRECISION,
  income              NUMERIC(14,2)
);


INSERT INTO owner.patients_owner (
  id, birthdate, ssn, drivers, passport,
  first, middle, last, maiden,
  address, city, fips, zip, lat, lon, income
)
SELECT
  id, birthdate, ssn, drivers, passport,
  first, middle, last, maiden,
  address, city, fips, zip, lat, lon, income
FROM public.patients
ON CONFLICT (id) DO UPDATE SET
  birthdate = EXCLUDED.birthdate,
  ssn       = EXCLUDED.ssn,
  drivers   = EXCLUDED.drivers,
  passport  = EXCLUDED.passport,
  first     = EXCLUDED.first,
  middle    = EXCLUDED.middle,
  last      = EXCLUDED.last,
  maiden    = EXCLUDED.maiden,
  address   = EXCLUDED.address,
  city      = EXCLUDED.city,
  fips      = EXCLUDED.fips,
  zip       = EXCLUDED.zip,
  lat       = EXCLUDED.lat,
  lon       = EXCLUDED.lon,
  income    = EXCLUDED.income;


-- SERVER
DROP TABLE IF EXISTS server.patients_server CASCADE;
CREATE TABLE server.patients_server (
  id                  TEXT PRIMARY KEY,
  deathdate           DATE,
  gender              TEXT,
  race                TEXT,
  ethnicity           TEXT,
  marital             TEXT,
  prefix              TEXT,
  suffix              TEXT,
  birthplace          TEXT,
  state               TEXT,
  county              TEXT,
  healthcare_expenses NUMERIC(14,2),
  healthcare_coverage NUMERIC(14,2),
  CONSTRAINT fk_pat_owner
    FOREIGN KEY (id) REFERENCES owner.patients_owner(id)
    ON DELETE CASCADE
);

INSERT INTO server.patients_server (
  id, deathdate, gender, race, ethnicity, marital,
  prefix, suffix, birthplace, state, county,
  healthcare_expenses, healthcare_coverage
)
SELECT
  id, deathdate, gender, race, ethnicity, marital,
  prefix, suffix, birthplace, state, county,
  healthcare_expenses, healthcare_coverage
FROM public.patients
ON CONFLICT (id) DO UPDATE SET
  deathdate= EXCLUDED.deathdate,gender= EXCLUDED.gender,race= EXCLUDED.race,ethnicity= EXCLUDED.ethnicity,
    marital= EXCLUDED.marital,prefix= EXCLUDED.prefix,suffix= EXCLUDED.suffix,birthplace= EXCLUDED.birthplace,state= EXCLUDED.state,
    county= EXCLUDED.county,healthcare_expenses = EXCLUDED.healthcare_expenses,healthcare_coverage = EXCLUDED.healthcare_coverage;

CREATE OR REPLACE VIEW public.patients_v AS
SELECT
  o.id,
  -- OWNER
  o.birthdate, o.ssn, o.drivers, o.passport,
  o.first, o.middle, o.last, o.maiden,
  o.address, o.city, o.fips, o.zip, o.lat, o.lon, o.income,
  -- SERVER
  s.deathdate, s.gender, s.race, s.ethnicity, s.marital,
  s.prefix, s.suffix, s.birthplace, s.state, s.county,
  s.healthcare_expenses, s.healthcare_coverage
FROM owner.patients_owner o
JOIN server.patients_server s USING (id);


CREATE INDEX IF NOT EXISTS idx_owner_city  ON owner.patients_owner(city);
CREATE INDEX IF NOT EXISTS idx_server_gender ON server.patients_server(gender);


ANALYZE owner.patients_owner;
ANALYZE server.patients_server;
