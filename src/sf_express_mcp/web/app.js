const orderForm = document.getElementById("orderForm");
const trackForm = document.getElementById("trackForm");
const credentialsForm = document.getElementById("credentialsForm");
const credentialsMessage = document.getElementById("credentialsMessage");
const orderResult = document.getElementById("orderResult");
const trackResult = document.getElementById("trackResult");
const dialog = document.getElementById("confirmDialog");
const orderSubmit = document.getElementById("orderSubmit");
let pendingOrder = null;
let orderLocked = false;
let sandboxAvailable = false;

const orderId = document.getElementById("orderId");

function ensureOrderId() {
  if (!orderId.value) orderId.value = `SMOKE-${Date.now()}-${crypto.randomUUID().slice(0, 8)}`;
  return orderId.value;
}

function textNode(tag, className, value) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = String(value ?? "");
  return element;
}

function value(data, key) {
  return String(data.get(key) ?? "").trim();
}

function contact(data, prefix) {
  const result = {
    name: value(data, `${prefix}_name`),
    mobile: value(data, `${prefix}_mobile`),
    province: value(data, `${prefix}_province`),
    city: value(data, `${prefix}_city`),
    address: value(data, `${prefix}_address`),
  };
  const county = value(data, `${prefix}_county`);
  if (county) result.county = county;
  return result;
}

function buildOrder() {
  const data = new FormData(orderForm);
  const result = {
    order_id: ensureOrderId(),
    sender: contact(data, "sender"),
    recipient: contact(data, "recipient"),
    cargo: [{name: value(data, "cargo_name"), count: Number(value(data, "cargo_count") || 1)}],
    parcel_qty: Number(value(data, "parcel_qty") || 1),
    pay_method: Number(value(data, "pay_method") || 1),
    request_pickup: data.has("request_pickup"),
  };
  const optionalNumber = ["total_weight_kg", "express_type_id"];
  const optionalText = ["monthly_card", "pickup_time", "remark"];
  for (const key of optionalNumber) if (value(data, key)) result[key] = Number(value(data, key));
  for (const key of optionalText) if (value(data, key)) result[key] = value(data, key);
  return result;
}

function orderSummary(order) {
  const pay = {1: "寄方付", 2: "收方付", 3: "第三方付"}[order.pay_method] || order.pay_method;
  return [
    `寄件人：${order.sender.name}  ${order.sender.mobile}`,
    `寄件地址：${order.sender.province} ${order.sender.city} ${order.sender.county || ""} ${order.sender.address}`,
    `收件人：${order.recipient.name}  ${order.recipient.mobile}`,
    `收件地址：${order.recipient.province} ${order.recipient.city} ${order.recipient.county || ""} ${order.recipient.address}`,
    `托寄物：${order.cargo[0].name} × ${order.cargo[0].count}；${order.parcel_qty} 个包裹`,
    `付款方式：${pay}；通知上门揽收：${order.request_pickup ? "是" : "否"}`,
  ].join("\n");
}

async function postJson(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  return await response.json();
}

function baseResult(target, title, status, response) {
  target.replaceChildren();
  target.hidden = false;
  const heading = textNode("div", "result-heading", "");
  heading.appendChild(textNode("h2", "", title));
  const badgeClass = status === "error" ? "result-badge error" : status === "outcome_unknown" ? "result-badge pending" : "result-badge";
  const badgeText = status === "error" ? "请求失败" : status === "outcome_unknown" ? "结果待核实" : "接口已响应";
  heading.appendChild(textNode("span", badgeClass, badgeText));
  target.appendChild(heading);
  if (response.error) {
    target.appendChild(textNode("p", "result-message", `${response.error.message || "请求失败"}（${response.error.code || "UNKNOWN"}）`));
    if (response.error.fields?.length) target.appendChild(textNode("p", "result-message", `检查字段：${response.error.fields.join("、")}`));
  }
  const details = document.createElement("details");
  details.appendChild(textNode("summary", "", "查看结构化响应"));
  details.appendChild(textNode("pre", "", JSON.stringify(response, null, 2)));
  return details;
}

function renderOrder(response) {
  const details = baseResult(orderResult, "下单结果", response.status, response);
  if (response.status === "created") {
    orderResult.appendChild(textNode("p", "result-message", "测试订单已提交。"));
    if (response.mapping_saved === false) orderResult.appendChild(textNode("p", "result-message", "本机保存订单号与运单号的对应关系失败，请自行记录。"));
    const list = textNode("div", "waybill-list", "");
    for (const number of response.waybill_numbers || []) list.appendChild(textNode("span", "waybill", number));
    orderResult.appendChild(list);
    if (response.waybill_numbers?.length) {
      trackForm.elements.tracking_type.value = "waybill";
      trackForm.elements.tracking_number.value = response.waybill_numbers[0];
    }
  } else if (response.status === "outcome_unknown") {
    orderResult.appendChild(textNode("p", "result-message", "顺丰可能已收到订单，但结果仍不确定。订单号已自动填入查件表单，请先查询核实，勿重复提交。"));
  }
  orderResult.appendChild(details);
  orderResult.scrollIntoView({behavior: "smooth", block: "nearest"});
}

function renderTrack(response) {
  const details = baseResult(trackResult, "查件结果", response.status, response);
  if (response.order_id) trackResult.appendChild(textNode("p", "result-message", `客户订单号：${response.order_id}`));
  if (response.status === "ok" || response.status === "no_events") {
    const label = response.waybill_number || response.tracking_number || "";
    trackResult.appendChild(textNode("p", "result-message", `${label} · ${response.events?.length || 0} 条轨迹`));
    if (!response.events?.length) {
      trackResult.appendChild(textNode("p", "result-message", "当前没有轨迹节点。沙盒订单通常不会发生真实运输。"));
    } else {
      const list = document.createElement("ol");
      list.className = "timeline";
      for (const event of response.events) {
        const item = document.createElement("li");
        item.appendChild(textNode("strong", "", event.remark || "轨迹更新"));
        item.appendChild(textNode("span", "", `${event.time || ""}  ${event.address || ""}  ${event.opcode ? `· ${event.opcode}` : ""}`));
        list.appendChild(item);
      }
      trackResult.appendChild(list);
    }
  }
  trackResult.appendChild(details);
  trackResult.scrollIntoView({behavior: "smooth", block: "nearest"});
}

async function loadStatus() {
  const mode = document.getElementById("modeLabel");
  const credentials = document.getElementById("configLabel");
  const signMode = document.getElementById("signModeLabel");
  try {
    const response = await fetch("/api/status", {cache: "no-store"});
    const status = await response.json();
    const sandbox = status.environment === "sandbox";
    sandboxAvailable = sandbox;
    mode.textContent = sandbox ? "沙盒环境" : `当前环境：${status.environment}`;
    mode.className = sandbox ? "ready" : "warning";
    credentials.textContent = status.credentials_configured ? "已填写（未验证）" : "未配置";
    credentials.className = status.credentials_configured ? "ready" : "warning";
    signMode.textContent = status.sign_mode === "simple" ? "简易 MD5" : "标准 MD5";
    orderSubmit.disabled = !sandbox || orderLocked;
    orderSubmit.title = sandbox ? "" : "网页端只允许沙盒下单";
  } catch {
    mode.textContent = "服务未连接";
    credentials.textContent = "状态未知";
    signMode.textContent = "状态未知";
    orderSubmit.disabled = true;
  }
}

credentialsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!credentialsForm.reportValidity()) return;
  const button = credentialsForm.querySelector('button[type="submit"]');
  const data = new FormData(credentialsForm);
  button.disabled = true;
  credentialsMessage.textContent = "保存中…";
  try {
    const response = await postJson("/api/config", {
      partner_id: value(data, "partner_id"),
      checkword: value(data, "checkword"),
      sign_mode: value(data, "sign_mode"),
    });
    credentialsMessage.textContent = response.error ? response.error.message : "已保存到当前服务，调用接口时才会验证";
    if (!response.error) {
      credentialsForm.reset();
      await loadStatus();
    }
  } catch {
    sandboxAvailable = false;
    credentialsMessage.textContent = "本机服务请求失败";
  } finally {
    credentialsForm.elements.checkword.value = "";
    button.disabled = false;
  }
});

document.getElementById("clearCredentials").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const response = await postJson("/api/config", {action: "clear"});
    credentialsMessage.textContent = response.error ? response.error.message : "网页配置已清除";
    credentialsForm.reset();
    await loadStatus();
  } catch {
    credentialsMessage.textContent = "本机服务请求失败";
  } finally {
    button.disabled = false;
  }
});

orderForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!orderForm.reportValidity()) return;
  pendingOrder = buildOrder();
  document.getElementById("orderSummary").textContent = orderSummary(pendingOrder);
  dialog.showModal();
});

document.getElementById("cancelOrder").addEventListener("click", () => dialog.close());
document.getElementById("confirmOrder").addEventListener("click", async () => {
  if (!pendingOrder) return;
  const order = pendingOrder;
  pendingOrder = null;
  dialog.close();
  orderSubmit.disabled = true;
  try {
    const response = await postJson("/api/order", order);
    renderOrder(response);
    if (response.status === "created") {
      orderForm.reset();
      orderId.value = "";
    } else if (response.status === "outcome_unknown") {
      orderLocked = true;
      trackForm.elements.tracking_type.value = "order";
      trackForm.elements.tracking_number.value = order.order_id;
    }
  } catch {
    renderOrder({status: "error", error: {code: "LOCAL_NETWORK", message: "本机服务请求失败"}});
    orderLocked = true;
    trackForm.elements.tracking_type.value = "order";
    trackForm.elements.tracking_number.value = order.order_id;
  } finally {
    orderSubmit.disabled = !sandboxAvailable || orderLocked;
  }
});

trackForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!trackForm.reportValidity()) return;
  const data = new FormData(trackForm);
  const query = {tracking_type: value(data, "tracking_type"), tracking_number: value(data, "tracking_number")};
  const button = trackForm.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    renderTrack(await postJson("/api/track", query));
  } catch {
    renderTrack({status: "error", error: {code: "LOCAL_NETWORK", message: "本机服务请求失败"}});
  } finally {
    button.disabled = false;
  }
});

loadStatus();
