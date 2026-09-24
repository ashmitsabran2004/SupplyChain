// ChainSight location + carrier graph
CREATE CONSTRAINT location_id IF NOT EXISTS
FOR (n:Location) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT carrier_id IF NOT EXISTS
FOR (c:Carrier) REQUIRE c.id IS UNIQUE;

CREATE INDEX location_kind IF NOT EXISTS FOR (n:Location) ON (n.kind);
CREATE INDEX location_name IF NOT EXISTS FOR (n:Location) ON (n.name);
