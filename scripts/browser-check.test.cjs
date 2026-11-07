const { test } = require("node:test");
const assert = require("node:assert/strict");
const { installable } = require("./browser-check.cjs");

test("CDP installability rejects actual errors and incomplete evidence", () => {
  const parsed = { data: "{}", errors: [] };
  assert.equal(installable(parsed, { installabilityErrors: [] }), true);
  assert.equal(installable(parsed, { installabilityErrors: [{ errorId: "no-icon-available" }] }), false);
  assert.equal(installable(parsed, {}), false);
  assert.equal(installable({ data: "", errors: [] }, { installabilityErrors: [] }), false);
  assert.equal(installable({ data: "{}", errors: [{ critical: 1 }] }, { installabilityErrors: [] }), false);
});
