CREATE INDEX trigger_event_signal  ON triggers_trigger
USING GIN(event, signals);
