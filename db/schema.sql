-- Core schema for the insurance mileage-split pipeline.
-- P0 = app off (personal), P1 = app on / not on a job, P2 = on a job.

CREATE TABLE cars (
    car_id          SERIAL PRIMARY KEY,
    vin             TEXT UNIQUE,
    license_plate   TEXT,
    gps_device_id   TEXT UNIQUE,
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE renters (
    renter_id       SERIAL PRIMARY KEY,
    full_name       TEXT NOT NULL,
    argyle_user_id  TEXT UNIQUE,
    ghl_contact_id  TEXT UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Which renter had which car, sourced from GoHighLevel.
CREATE TABLE rental_assignments (
    assignment_id   SERIAL PRIMARY KEY,
    car_id          INTEGER NOT NULL REFERENCES cars(car_id),
    renter_id       INTEGER NOT NULL REFERENCES renters(renter_id),
    start_date      DATE NOT NULL,
    end_date        DATE,                -- NULL = still active
    source          TEXT NOT NULL DEFAULT 'gohighlevel',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_rental_assignments_car_dates ON rental_assignments (car_id, start_date, end_date);

-- One row per GPS trip. Timestamps are always stored in UTC;
-- the GPS source reports Florida local time and must be converted on load.
CREATE TABLE trips (
    trip_id         SERIAL PRIMARY KEY,
    car_id          INTEGER NOT NULL REFERENCES cars(car_id),
    start_time_utc  TIMESTAMPTZ NOT NULL,
    end_time_utc    TIMESTAMPTZ NOT NULL,
    miles           NUMERIC(8,2) NOT NULL,
    source          TEXT NOT NULL,
    raw_payload     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (car_id, start_time_utc, end_time_utc)
);
CREATE INDEX idx_trips_car_time ON trips (car_id, start_time_utc);

CREATE TYPE app_status AS ENUM ('off', 'on_available', 'on_job');

-- Renter app-status timeline, sourced from Argyle (native UTC).
CREATE TABLE app_status_intervals (
    interval_id     SERIAL PRIMARY KEY,
    renter_id       INTEGER NOT NULL REFERENCES renters(renter_id),
    start_time_utc  TIMESTAMPTZ NOT NULL,
    end_time_utc    TIMESTAMPTZ NOT NULL,
    status          app_status NOT NULL,
    source          TEXT NOT NULL DEFAULT 'argyle',
    raw_payload     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_status_renter_time ON app_status_intervals (renter_id, start_time_utc);

-- One row per car per month, the output of the calculation engine.
CREATE TABLE monthly_reports (
    report_id       SERIAL PRIMARY KEY,
    car_id          INTEGER NOT NULL REFERENCES cars(car_id),
    report_month    DATE NOT NULL,        -- first day of the month
    p0_miles        NUMERIC(9,2) NOT NULL,
    p1_miles        NUMERIC(9,2) NOT NULL,
    p2_miles        NUMERIC(9,2) NOT NULL,
    total_miles     NUMERIC(9,2) NOT NULL,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (car_id, report_month)
);
