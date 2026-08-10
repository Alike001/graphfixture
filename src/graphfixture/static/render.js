const text = (tag, className, value) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = value ?? "";
  return node;
};

const card = (title, wide = false) => {
  const node = text("article", `evidence-card${wide ? " wide" : ""}`, "");
  node.append(text("h2", "", title));
  return node;
};

const table = (rows, missingIds = []) => {
  if (!rows.length) return text("div", "empty-table", "No related rows. This absence is part of the reproducer.");
  const wrap = text("div", "data-table-wrap", "");
  const grid = text("table", "data-table", "");
  const columns = Object.keys(rows[0]);
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  columns.forEach((column) => headRow.append(text("th", "", column)));
  head.append(headRow);
  const body = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    columns.forEach((column) => {
      const value = row[column] ?? "null";
      const className = missingIds.includes(String(row.customer_id)) ? "missing" : "";
      tr.append(text("td", className, String(value)));
    });
    body.append(tr);
  });
  grid.append(head, body);
  wrap.append(grid);
  return wrap;
};

const definitionList = (pairs) => {
  const list = text("dl", "key-value", "");
  pairs.forEach(([key, value]) => list.append(text("dt", "", key), text("dd", "", String(value))));
  return list;
};

const sqlBlock = (sql, variant) => {
  const block = text("pre", "code-block", "");
  sql.trim().split("\n").forEach((line) => {
    let className = "code-line";
    if (variant === "broken" && line.includes("INNER JOIN orders")) className += " failure-line";
    if (variant === "fixed" && line.includes("LEFT JOIN orders")) className += " fixed-line";
    block.append(text("span", className, line));
  });
  return block;
};

function verificationView(proof) {
  const grid = text("div", "evidence-grid", "");
  const rule = card("Rule");
  rule.append(
    text("p", "rule-title", proof.contract.title),
    text("p", "rule-source", `Source: ${proof.contract.source_urn}`),
    definitionList([
      ["Expected", `Every ${proof.contract.active_value} customer appears exactly once`],
      ["Compared field", proof.contract.key_field],
    ]),
  );
  const reproducer = card("Minimal reproducer");
  Object.entries(proof.reproducer).forEach(([name, rows]) => {
    reproducer.append(text("h3", "", name), table(rows, proof.missing_ids));
  });
  const execution = card("Execution");
  execution.append(text("h3", "", "SQL"));
  const code = sqlBlock(proof.sql, proof.variant);
  execution.append(code, text("h3", "", "Expected output"), table(proof.expected_rows, proof.missing_ids));
  execution.append(text("h3", "", "Actual output"), table(proof.execution.rows, proof.missing_ids));
  grid.append(rule, reproducer, execution);
  return grid;
}

function overviewView(proof, selected) {
  const grid = text("div", "evidence-grid", "");
  const panel = card(proof.stages.find((stage) => stage.key === selected).label, true);
  if (selected === "datahub_context") {
    panel.append(definitionList([
      ["Mode", proof.source_mode],
      ["Captured", proof.captured_at],
      ["Datasets", proof.tables.length],
      ["Lineage edges", proof.lineage.length],
    ]));
    panel.append(text("h3", "", "Graph assets"));
    proof.tables.forEach((item) => panel.append(text("p", "mono", item.urn)));
  } else if (selected === "constraints") {
    panel.append(definitionList(Object.entries(proof.contract)));
  } else if (selected === "fixtures") {
    Object.entries(proof.fixtures).forEach(([name, rows]) => {
      panel.append(text("h3", "", `${name} · ${rows.length} rows`), table(rows, proof.missing_ids));
    });
  } else if (selected === "duckdb") {
    panel.append(text("h3", "", "Executed SQL"), sqlBlock(proof.sql, proof.variant));
    panel.append(text("h3", "", "DuckDB output"), table(proof.execution.rows, proof.missing_ids));
  } else {
    const receipt = proof.writeback;
    panel.append(text("div", `receipt-proof${receipt ? "" : " unavailable"}`, receipt ? "Receipt stored and read back from DataHub." : "Write-back is unavailable in offline synthetic replay."));
    panel.append(definitionList([
      ["Document URN", receipt?.document_urn ?? "Unavailable"],
      ["Evidence digest", receipt?.evidence_digest ?? proof.digest],
      ["Read-back verified", receipt?.verified ?? false],
    ]));
  }
  grid.append(panel);
  return grid;
}

export function renderEvidence(target, proof, selected) {
  target.replaceChildren(selected === "verification" ? verificationView(proof) : overviewView(proof, selected));
}
