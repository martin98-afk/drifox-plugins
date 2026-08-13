#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");
const skill = read("SKILL.md");
const skillContract = read("references/skill-contract.md");
const contract = read("references/visual-workspace-contract.md");
const imageFlow = read("references/image-generation-workflow.md");
const interaction = read("references/interactive-mvp-decision-system.md");
const adapterDoc = read("references/provider-adapters/cowart.md");
const adapter = JSON.parse(read("assets/visual-workspace-adapters/cowart.json"));
const sessionSchema = JSON.parse(read("contracts/visual-workspace-session.schema.json"));
const offerEvals = JSON.parse(read("evals/visual-workspace-offer.eval.json"));

const failures = [];
const requireText = (label, text, needles) => {
  for (const needle of needles) {
    if (!text.includes(needle)) failures.push(`${label}: missing ${needle}`);
  }
};

requireText("generic contract", contract, [
  "机会研究 -> 营销决策 -> 逐页视觉导演 -> Image2 Brief",
  "3:4",
  "mobile_thumbnail_check",
  "accepted_asset",
  "只返修失败页",
  "状态只能写 `attempted`",
  "persisted_verified",
  "持久化 snapshot 的 SHA-256",
  "`accepted_asset` 只能在对应 `workspace_placement.status = persisted_verified` 后",
  "静态合同校验器或 eval 通过"
  ,"封面首稿已经出来"
  ,"同一 `offer_stage + value_fingerprint` 最多询问一次"
  ,"Markdown 降级卡"
]);
for (const [label, text] of [
  ["SKILL.md", skill],
  ["skill contract", skillContract],
  ["visual workspace contract", contract],
  ["image flow", imageFlow],
  ["interaction", interaction]
]) {
  if (/CowArt|AI Slides/i.test(text)) {
    failures.push(`${label}: provider-specific names leaked into generic control rules`);
  }
}

requireText("image flow", imageFlow, [
  "视觉工作台不在上述 1-4 级路线中",
  "不能在 Image2 失败后",
  "逐页资产清单"
]);
requireText("interaction", interaction, [
  "工作台中的选中、拖放或槽位 id 不算选择证据",
  "AskUserQuestion",
  "只返修失败页"
]);
requireText("CowArt adapter", adapterDoc, [
  "CowArt `0.1.20`",
  "版本号只用于说明",
  "capability probe",
  "render_cowart_canvas_widget",
  "get_cowart_selection",
  "insert_cowart_image",
  "get_cowart_canvas_state",
  "正常路径不启动 localhost、本地网页服务或浏览器",
  "`canvasDir` 必须解析为 `<projectDir>/canvas`",
  "只有三项都通过，状态才能从 `attempted` 提升为 `persisted_verified`",
  "`replaceAiImageHolder: false`、`placement: \"right\"`",
  "静态 `check-visual-workspace-contract.mjs` 通过只证明",
  "不得使用 AI Slides 的 16:9",
  "request_user_input",
  "原图旁边",
  "accepted_asset",
  "不得启动 CowArt 当作第 2 级生成器"
  ,"面向用户的选择文案"
  ,"offered_pending"
  ,"opened_verified"
]);

if (adapter.provider_role !== "visual_workspace") failures.push("adapter: provider_role must be visual_workspace");
if (adapter.target_version_metadata !== "0.1.20") failures.push("adapter: target version metadata must be 0.1.20");
if (adapter.version_is_enablement_evidence !== false) failures.push("adapter: version metadata must not enable the adapter");
if (adapter.generation_route_tier !== null) failures.push("adapter: generation_route_tier must be null");
if (adapter.may_rescue_generation_failure !== false) failures.push("adapter: may_rescue_generation_failure must be false");
if (adapter.canvas?.required_aspect_ratio !== "3:4") failures.push("adapter: required aspect ratio must be 3:4");
if (!adapter.canvas?.forbidden_modes?.includes("AI Slides 16:9")) failures.push("adapter: AI Slides 16:9 must be forbidden");
if (!adapter.capabilities?.includes("post_insert_persistence_readback")) failures.push("adapter: persistence readback capability must be declared");
const requiredTools = ["render_cowart_canvas_widget", "get_cowart_selection", "insert_cowart_image", "get_cowart_canvas_state"];
const configuredRequiredTools = adapter.enablement?.required_tools ?? [];
if (adapter.enablement?.mode !== "capability_probe") failures.push("adapter: enablement mode must be capability_probe");
for (const tool of requiredTools) {
  if (!configuredRequiredTools.includes(tool)) failures.push(`adapter: missing required capability ${tool}`);
}
if (configuredRequiredTools.some((tool) => !requiredTools.includes(tool))) failures.push("adapter: required capability set contains unexpected tools");
for (const tool of ["save_cowart_canvas_state", "save_cowart_reference_image", "read_cowart_page_asset"]) {
  if (!Object.values(adapter.native_tool_mappings ?? {}).includes(tool)) failures.push(`adapter: missing optional/conditional capability mapping ${tool}`);
}
if (adapter.native_tool_mappings?.open_widget !== "render_cowart_canvas_widget") failures.push("adapter: native widget mapping is stale");
if (adapter.native_tool_mappings?.read_selection_and_holder_contract !== "get_cowart_selection") failures.push("adapter: selection mapping is stale");
if (adapter.native_tool_mappings?.insert_or_replace_bitmap !== "insert_cowart_image") failures.push("adapter: image insertion mapping is stale");
if (adapter.native_tool_mappings?.post_insert_state_readback !== "get_cowart_canvas_state") failures.push("adapter: post-insert readback mapping is missing");
if (adapter.normal_transport !== "native_codex_widget_mcp") failures.push("adapter: normal transport must be native widget MCP");
if (adapter.legacy_localhost_browser_path_is_normal !== false) failures.push("adapter: legacy localhost/browser path must not be normal");
if (adapter.unsupported_host_behavior !== "continue_existing_host_native_image_and_choice_route") failures.push("adapter: unsupported hosts must continue the existing route");

const offerPolicy = adapter.offer_policy ?? {};
const offerStates = ["not_offered", "offered_pending", "accepted", "declined", "unavailable", "launch_failed", "opened_verified"];
if (offerPolicy.offer_only_after_visible_value !== true || offerPolicy.primary_offer_stage !== "cover_first_visible_candidate") failures.push("adapter: offer must wait for the first visible 3:4 cover candidate");
for (const prerequisite of ["opportunity_research_complete", "marketing_decision_complete", "page_directions_complete", "image2_brief_complete", "visible_3_4_cover_candidate"]) {
  if (!offerPolicy.required_primary_prerequisites?.includes(prerequisite)) failures.push(`adapter: offer prerequisites missing ${prerequisite}`);
}
for (const state of offerStates) {
  if (!offerPolicy.states?.includes(state)) failures.push(`adapter: offer states missing ${state}`);
  if (!sessionSchema.properties?.status?.enum?.includes(state)) failures.push(`session schema: status enum missing ${state}`);
}
if (offerPolicy.same_stage_offer_limit !== 1 || offerPolicy.dedupe_key !== "offer_stage+value_fingerprint") failures.push("adapter: same stage offer must be deduplicated");
for (const gate of ["different_offer_stage", "new_value_reason", "new_value_evidence_sha256", "changed_value_fingerprint"]) {
  if (!offerPolicy.cross_stage_reoffer_requires?.includes(gate)) failures.push(`adapter: cross-stage reoffer missing ${gate}`);
}
if (offerPolicy.markdown_fallback_must_stop_and_wait !== true) failures.push("adapter: Markdown fallback must stop and wait");
if (offerPolicy.explicit_auto_permission_is_human_confirmation !== false) failures.push("adapter: explicit auto permission must not prove human confirmation");
for (const status of ["declined", "unavailable", "launch_failed"]) {
  if (!offerPolicy.continue_existing_route_on?.includes(status)) failures.push(`adapter: ${status} must continue the existing route`);
}
for (const text of ["封面首稿已经出来", "3:4", "打开工作台（推荐）", "暂不打开，继续生成", "结果不会少"]) {
  if (!JSON.stringify(offerPolicy.user_copy ?? {}).includes(text)) failures.push(`adapter: user-facing copy missing ${text}`);
}
if (/CowArt|MCP|widget|holder|shape/i.test(JSON.stringify(offerPolicy.user_copy ?? {}))) failures.push("adapter: user-facing copy leaks provider or implementation terms");
if (!sessionSchema.required?.includes("value_fingerprint") || sessionSchema.properties?.same_stage_offer_count?.maximum !== 1) failures.push("session schema: dedupe fields are incomplete");
if (!sessionSchema.properties?.decision_surface?.enum?.includes("markdown_fallback") || !sessionSchema.properties?.decision_surface?.enum?.includes("explicit_auto_permission")) failures.push("session schema: decision surfaces are incomplete");

const capabilityProbeEnables = (advertisedTools) => requiredTools.every((tool) => advertisedTools.includes(tool));
if (!capabilityProbeEnables(requiredTools)) failures.push("probe fixture: complete native capability set should enable");
if (capabilityProbeEnables(["render_cowart_canvas_widget", "get_cowart_selection", "insert_cowart_image"])) failures.push("probe fixture: missing state readback capability must disable");
if (capabilityProbeEnables(["0.1.20"])) failures.push("probe fixture: version metadata alone must not enable");
for (const boundary of ["persisted_placement", "generation", "quality", "acceptance"]) {
  if (!adapter.proof_boundaries?.insert_result_ids_do_not_prove?.includes(boundary)) {
    failures.push(`adapter: insert result ids must not prove ${boundary}`);
  }
}
if (!adapter.proof_boundaries?.insert_result_ids_prove?.includes("attempted")) failures.push("adapter: insert ids must prove attempted only");
if (adapter.proof_boundaries?.completed_placement_status !== "persisted_verified") failures.push("adapter: completed placement must be persisted_verified");
for (const evidence of ["post_insert_get_cowart_canvas_state", "shape_id_readback_match", "asset_url_or_path_readback_match", "persisted_snapshot_sha256"]) {
  if (!adapter.proof_boundaries?.completed_placement_requires?.includes(evidence)) failures.push(`adapter: completed placement missing ${evidence}`);
}
if (adapter.proof_boundaries?.final_asset_field !== "accepted_asset") failures.push("adapter: final asset field must be accepted_asset");
if (adapter.proof_boundaries?.static_validator_is_live_host_proof !== false) failures.push("adapter: static validator must not claim live host proof");

const pathPolicy = adapter.path_policy ?? {};
if (pathPolicy.project_dir_source !== "current_user_workspace") failures.push("adapter: projectDir must bind to current user workspace");
if (pathPolicy.default_canvas_dir !== "<projectDir>/canvas") failures.push("adapter: default canvasDir must be <projectDir>/canvas");
if (pathPolicy.custom_canvas_dir_default !== "forbidden") failures.push("adapter: custom canvasDir must default to forbidden");
if (pathPolicy.custom_canvas_dir_must_remain_within_project_dir !== true) failures.push("adapter: custom canvasDir must remain within projectDir");
for (const gate of ["explicit_user_authorization", "normalized_path_containment", "realpath_and_symlink_containment"]) {
  if (!pathPolicy.custom_canvas_dir_exception_requires?.includes(gate)) failures.push(`adapter: custom canvasDir missing gate ${gate}`);
}
if (pathPolicy.record_resolved_project_dir !== true || pathPolicy.record_resolved_canvas_dir !== true) failures.push("adapter: resolved project/canvas paths must be recorded");

const holderPolicy = adapter.insert_policies?.verified_ai_image_holder;
if (holderPolicy?.replaceAiImageHolder !== true || !holderPolicy?.requires?.includes("exactly_one_selected_ai_image_holder")) failures.push("adapter: holder replacement requires a verified single AI image holder");
const annotationPolicy = adapter.insert_policies?.annotation_before_after;
if (annotationPolicy?.replaceAiImageHolder !== false || annotationPolicy?.placement !== "right" || annotationPolicy?.preserve_original !== true || annotationPolicy?.preserve_annotations !== true) {
  failures.push("adapter: annotation branch must preserve evidence and place right without replacement");
}

const hashPattern = /^[a-f0-9]{64}$/;
const isContained = (projectDir, canvasDir) => {
  const project = path.win32.resolve(projectDir);
  const canvas = path.win32.resolve(canvasDir);
  const relative = path.win32.relative(project, canvas);
  return relative !== "" && relative !== ".." && !relative.startsWith(`..${path.win32.sep}`) && !path.win32.isAbsolute(relative);
};
const pathBindingAccepts = (event) => {
  if (!event.resolved_project_dir || !event.resolved_canvas_dir) return false;
  const expectedDefault = path.win32.join(path.win32.resolve(event.resolved_project_dir), "canvas");
  if (path.win32.resolve(event.resolved_canvas_dir) === expectedDefault) return true;
  return event.custom_canvas_dir === true
    && event.explicit_user_authorization === true
    && event.realpath_and_symlink_containment === true
    && isContained(event.resolved_project_dir, event.resolved_canvas_dir);
};
const placementComplete = (event) => {
  if (!pathBindingAccepts(event)) return false;
  if (event.insert_attempt?.status !== "attempted") return false;
  const readback = event.state_readback;
  if (readback?.tool !== "get_cowart_canvas_state" || readback?.status !== "persisted_verified") return false;
  if (readback.shape_id !== event.insert_attempt.returned_shape_id) return false;
  if (readback.asset_url_or_path !== event.insert_attempt.returned_asset_url_or_path) return false;
  if (!hashPattern.test(readback.persisted_snapshot_sha256 || "")) return false;
  if (event.branch === "verified_ai_image_holder") {
    return event.exactly_one_selected_ai_image_holder === true && event.aspect_ratio === "3:4" && event.replaceAiImageHolder === true;
  }
  if (event.branch === "annotation_before_after") {
    return event.replaceAiImageHolder === false && event.placement === "right" && event.original_preserved === true && event.annotations_preserved === true;
  }
  return event.replaceAiImageHolder === false;
};

const goodPlacement = {
  resolved_project_dir: "D:\\workspace",
  resolved_canvas_dir: "D:\\workspace\\canvas",
  branch: "verified_ai_image_holder",
  exactly_one_selected_ai_image_holder: true,
  aspect_ratio: "3:4",
  replaceAiImageHolder: true,
  insert_attempt: { status: "attempted", returned_shape_id: "shape:cover", returned_asset_url_or_path: "/page-assets/page-1/cover.png" },
  state_readback: { tool: "get_cowart_canvas_state", status: "persisted_verified", shape_id: "shape:cover", asset_url_or_path: "/page-assets/page-1/cover.png", persisted_snapshot_sha256: "a".repeat(64) }
};
if (!placementComplete(goodPlacement)) failures.push("placement fixture: verified holder with readback should complete");
if (placementComplete({ ...goodPlacement, state_readback: undefined })) failures.push("placement fixture: insert ids without readback must remain attempted");
if (placementComplete({ ...goodPlacement, resolved_canvas_dir: "E:\\outside", custom_canvas_dir: true, explicit_user_authorization: false, realpath_and_symlink_containment: false })) failures.push("placement fixture: unsafe canvasDir must be rejected");
if (placementComplete({ ...goodPlacement, branch: "annotation_before_after", replaceAiImageHolder: true, placement: "right", original_preserved: true, annotations_preserved: true })) failures.push("placement fixture: annotation replacement must be rejected");

const requiredOfferCases = new Map([
  ["recommended-open", "accepted"],
  ["skip-and-continue", "accepted"],
  ["runtime-unavailable", "accepted"],
  ["launch-failed-non-blocking", "accepted"],
  ["same-stage-deduplicated", "accepted"],
  ["cross-stage-new-value-reoffer", "accepted"],
  ["explicit-auto-permission", "accepted"],
  ["markdown-fallback-waits", "accepted"],
  ["offer-before-visible-cover", "rejected"],
  ["same-stage-repeat", "rejected"],
  ["cross-stage-without-new-value", "rejected"],
  ["opened-without-state-readback", "rejected"],
  ["auto-permission-claims-human-confirmed", "rejected"],
  ["markdown-claims-native-popup", "rejected"],
]);

const offerScenarioAccepts = (id) => {
  const base = {
    opportunityResearchComplete: true,
    marketingDecisionComplete: true,
    pageDirectionsComplete: true,
    image2BriefComplete: true,
    visibleSampleSha256: "a".repeat(64),
    aspectRatio: "3:4",
    offerStage: "cover_first_visible_candidate",
    previousOfferStage: null,
    previousValueFingerprint: null,
    valueFingerprint: "a".repeat(64),
    sameStageOfferCount: 1,
    secondOfferAttempted: false,
    status: "accepted",
    decisionSurface: "request_user_input",
    decisionEvidence: { kind: "native_choice_return", humanConfirmationProven: true },
    newValueReason: null,
    newValueEvidenceSha256: null,
    launchEvidence: null,
    stateReadback: null,
    continuation: "launch_workspace",
    claimedNativePopup: true,
  };
  const scenario = { ...base };
  if (id === "recommended-open") {
    scenario.status = "opened_verified";
    scenario.launchEvidence = { tool: "render_cowart_canvas_widget" };
    scenario.stateReadback = { tool: "get_cowart_canvas_state", shapeId: "shape:cover", assetPath: "/page-assets/cover.png", snapshotSha256: "b".repeat(64) };
    scenario.continuation = "continue_existing_route";
  }
  if (id === "skip-and-continue") { scenario.status = "declined"; scenario.continuation = "continue_existing_route"; }
  if (id === "runtime-unavailable") { scenario.status = "unavailable"; scenario.decisionSurface = "none"; scenario.sameStageOfferCount = 0; scenario.decisionEvidence = null; scenario.continuation = "continue_existing_route"; }
  if (id === "launch-failed-non-blocking") { scenario.status = "launch_failed"; scenario.launchEvidence = { tool: "render_cowart_canvas_widget", failed: true }; scenario.continuation = "continue_existing_route"; }
  if (id === "same-stage-deduplicated") { scenario.status = "declined"; scenario.continuation = "continue_existing_route"; }
  if (id === "cross-stage-new-value-reoffer") { scenario.offerStage = "cover_revision_comparison"; scenario.previousOfferStage = "cover_first_visible_candidate"; scenario.previousValueFingerprint = "c".repeat(64); scenario.newValueReason = "revised cover candidate is ready for before/after comparison"; scenario.newValueEvidenceSha256 = "d".repeat(64); }
  if (id === "explicit-auto-permission") { scenario.decisionSurface = "explicit_auto_permission"; scenario.decisionEvidence = { kind: "explicit_auto_permission", humanConfirmationProven: false }; }
  if (id === "markdown-fallback-waits") { scenario.status = "offered_pending"; scenario.decisionSurface = "markdown_fallback"; scenario.decisionEvidence = null; scenario.continuation = "wait_for_markdown_reply"; scenario.claimedNativePopup = false; }
  if (id === "offer-before-visible-cover") scenario.visibleSampleSha256 = null;
  if (id === "same-stage-repeat") { scenario.sameStageOfferCount = 2; scenario.secondOfferAttempted = true; }
  if (id === "cross-stage-without-new-value") { scenario.offerStage = "cover_revision_comparison"; scenario.previousOfferStage = "cover_first_visible_candidate"; scenario.previousValueFingerprint = scenario.valueFingerprint; }
  if (id === "opened-without-state-readback") { scenario.status = "opened_verified"; scenario.launchEvidence = { tool: "render_cowart_canvas_widget" }; scenario.stateReadback = null; scenario.continuation = "continue_existing_route"; }
  if (id === "auto-permission-claims-human-confirmed") { scenario.decisionSurface = "explicit_auto_permission"; scenario.decisionEvidence = { kind: "explicit_auto_permission", humanConfirmationProven: true }; }
  if (id === "markdown-claims-native-popup") { scenario.status = "offered_pending"; scenario.decisionSurface = "markdown_fallback"; scenario.decisionEvidence = null; scenario.continuation = "wait_for_markdown_reply"; scenario.claimedNativePopup = true; }

  const primaryReady = scenario.opportunityResearchComplete && scenario.marketingDecisionComplete && scenario.pageDirectionsComplete && scenario.image2BriefComplete && hashPattern.test(scenario.visibleSampleSha256 || "") && scenario.aspectRatio === "3:4";
  if (!primaryReady && !["not_offered", "unavailable"].includes(scenario.status)) return false;
  if (scenario.sameStageOfferCount > 1 || scenario.secondOfferAttempted) return false;
  if (["cover_revision_comparison", "failed_page_revision_comparison"].includes(scenario.offerStage)) {
    if (scenario.previousOfferStage === scenario.offerStage || !scenario.newValueReason || !hashPattern.test(scenario.newValueEvidenceSha256 || "") || scenario.previousValueFingerprint === scenario.valueFingerprint) return false;
  }
  if (scenario.decisionEvidence?.kind === "explicit_auto_permission" && scenario.decisionEvidence.humanConfirmationProven !== false) return false;
  if (scenario.decisionEvidence?.kind === "native_choice_return" && scenario.decisionEvidence.humanConfirmationProven !== true) return false;
  if (scenario.decisionSurface === "markdown_fallback" && (scenario.status !== "offered_pending" || scenario.continuation !== "wait_for_markdown_reply" || scenario.claimedNativePopup !== false)) return false;
  if (["declined", "unavailable", "launch_failed"].includes(scenario.status) && scenario.continuation !== "continue_existing_route") return false;
  if (scenario.status === "opened_verified") {
    if (scenario.launchEvidence?.tool !== "render_cowart_canvas_widget" || scenario.stateReadback?.tool !== "get_cowart_canvas_state") return false;
    if (!scenario.stateReadback.shapeId || !scenario.stateReadback.assetPath || !hashPattern.test(scenario.stateReadback.snapshotSha256 || "")) return false;
  }
  return true;
};

for (const [id, expected] of requiredOfferCases) {
  const item = offerEvals.cases?.find((entry) => entry.id === id);
  if (!item || item.expected !== expected) failures.push(`offer eval: ${id} must expect ${expected}`);
  const actual = offerScenarioAccepts(id) ? "accepted" : "rejected";
  if (actual !== expected) failures.push(`offer eval: ${id} produced ${actual}; expected ${expected}`);
}

if (failures.length) {
  console.error("visual-workspace contract FAIL");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("visual-workspace contract PASS");
console.log(`provider-neutral control, ${requiredOfferCases.size} offer-state regressions, CowArt persistence readback, path containment, safe replacement, and annotation preservation verified`);
