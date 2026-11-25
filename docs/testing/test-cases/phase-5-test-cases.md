# XploVoice test cases: Phase 5 (knowledge, workflows, tools, integrations)

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys

Synthetic data only. No PHI. Each automated case names the pytest test that checks it (`apps/api/tests`); manual cases are run in the browser.

28 test cases.

| ID | Area | Test case | Preconditions | Steps | Expected result | Type / automated test |
|---|---|---|---|---|---|---|
| TC-P5-01 | Knowledge | Upload is scanned, typed by content, chunked and searchable | Owner signed in | Upload text, PDF and Word files; upload EICAR and a renamed executable | Good files ready and searchable; bad files rejected and never stored | Auto: test_documents_are_scanned_typed_by_content_chunked_and_searchable; Manual: Knowledge base page |
| TC-P5-02 | Knowledge | Chunks keep paragraphs and split long ones with overlap | None | Chunk a long text | Paragraph-aware chunks of about 900 characters with sentence overlap | Auto: test_chunking_keeps_paragraphs_and_splits_long_ones_with_overlap |
| TC-P5-03 | Knowledge | Scanner required outside development | Environment set to production-like, no ClamAV | Upload a file | 503, nothing stored | Auto: test_scanner_is_required_outside_development |
| TC-P5-04 | Isolation (O6) | Retrieval reads only own tenant, granted and active knowledge | Two tenants with similar text; ungranted and archived knowledge bases | Ask the agent a matching question | Only the granted, active knowledge base of the caller's tenant is used | Auto: test_retrieval_reads_only_the_agents_own_tenant_and_granted_active_knowledge |
| TC-P5-05 | Knowledge | Retrieved text treated as data | Document containing an instruction | Ask a question that retrieves it | Passage sent in a separate reference block marked as data, not instructions | Auto: test_retrieved_text_is_marked_as_data_not_instructions |
| TC-P5-06 | Knowledge | Search a knowledge base in the browser | Knowledge base with a FAQ | Search "Is parking free?" | Matching passage with its document name and score | Manual: Knowledge base page |
| TC-P5-07 | Booking | Agent books by chat; everything recorded | Calendar granted; mock models | Chat: book an appointment, my name is Asha | Availability checked, slot booked, tool uses, events and audit recorded | Auto: test_booking_by_chat_runs_tools_server_side_and_records_everything; Manual: Test call page |
| TC-P5-08 | Booking | Availability respects hours, notice, holidays and bookings | Calendar with hours | Ask for slots on various days | Closed days, past notice, holidays and booked slots are excluded | Auto: test_availability_respects_hours_notice_holidays_and_bookings |
| TC-P5-09 | Booking | Org-wide holiday closes business hours | Holiday with no calendar | Check business hours that day | Agent is closed | Auto: test_org_holidays_close_agent_business_hours |
| TC-P5-10 | Booking | Create a calendar and book by hand | Owner signed in | Create calendar; pick a free time; book | Appointment appears under Upcoming | Manual: Appointments page |
| TC-P5-11 | Tools (O7) | Tools run only when granted, enabled, valid and once | Agent version with some tools | Call ungranted, disabled, invalid and repeated tools | Refused with a reason; a repeated request does not run twice | Auto: test_tools_run_only_when_granted_enabled_valid_and_never_twice |
| TC-P5-12 | Tools (O7) | Sensitive actions wait for a person | Cancel needs approval | Ask to cancel; approve as operator; deny another; second approver | Pending until approved; runs once; denial recorded; viewer cannot approve | Auto: test_sensitive_actions_wait_for_a_person; Manual: Business tools page |
| TC-P5-13 | Tools | Tool failures are contained | Tool made to fail or time out | Use the tool on a chat | Agent continues; failure recorded; no crash | Auto: test_tool_failures_are_contained |
| TC-P5-14 | Tools | Model without tool support still answers | Model routing without tool-capable models | Chat | Answers without tools | Auto: test_mock_model_without_tool_support_still_answers |
| TC-P5-15 | Tools | Tools during a voice call go through the worker API | Voice call in progress | Worker asks the LLM endpoint | Tool runs on the server; result streamed as an event | Auto: test_tools_during_a_voice_call_go_through_the_worker_api |
| TC-P5-16 | Leads | Leads and follow-ups from a chat | create_lead granted | Chat: I'm interested, call me back | Lead with score and a follow-up created | Auto: test_leads_and_follow_ups_from_a_chat; Manual: Leads, Follow-ups pages |
| TC-P5-17 | Tickets | Tickets from a tool and from escalation | create_ticket granted | Report a problem; ask for a person on a call | Ticket created; one high-priority escalation ticket per call | Auto: test_tickets_from_tools_and_from_escalation; Manual: Tickets page |
| TC-P5-18 | Messages | Only approved templates sent; never claimed delivered | Draft and approved templates; no SMS provider | Send from draft, unknown placeholder, approved | Draft refused; unknown placeholder refused; approved one kept as held with reason | Auto: test_only_approved_messages_are_sent_and_never_claimed_delivered; Manual: Messages page |
| TC-P5-19 | Integrations | Webhook URLs must be public https | Admin signed in | Add http, private IP, localhost, credentials, odd port | All refused with a clear message | Auto: test_webhook_urls_must_be_public_https; Manual: Integrations page |
| TC-P5-20 | Integrations | Events signed, delivered, retried and isolated | Webhook subscribed; test receiver | Book an appointment; receiver fails once | Signed request with delivery id; retried; other tenant's events never sent | Auto: test_events_are_signed_delivered_retried_and_isolated |
| TC-P5-21 | Integrations | Delivery marked dead after 8 attempts | Receiver always fails | Run the dispatcher repeatedly | Status dead after 8 attempts | Auto: test_dead_after_max_attempts |
| TC-P5-22 | Integrations | Signing secret shown once; rotate | Admin signed in | Add webhook; reload; rotate | Secret shown once only; new secret on rotate | Manual: Integrations page |
| TC-P5-23 | Roles | Role permissions for Phase 5 | Members with each role | Use each Phase 5 endpoint | Allowed or 403 as per the role table | Auto: test_role_permissions_for_phase_5 |
| TC-P5-24 | Adapters | OpenAI tool calls parsed from the stream | Simulated OpenAI stream | Stream a reply with tool calls | Tool name and arguments assembled | Auto: test_openai_tool_calls_are_parsed_from_the_stream |
| TC-P5-25 | Adapters | Anthropic tool-use blocks parsed; results sent back | Simulated Anthropic stream | Stream; send tool results | Tool use parsed; results sent as tool_result blocks | Auto: test_anthropic_tool_use_blocks_are_parsed_and_results_sent_back |
| TC-P5-26 | Agent builder | Grant knowledge, tools and a calendar | Knowledge base and calendar exist | Tick them under Knowledge and tools; save | New version saved; readiness passes | Auto: test_all_builder_fields_round_trip; Manual: Agent builder |
| TC-P5-27 | Chat test | Text chat does not satisfy the publish test | Agent with a chat only | Try to publish | Publish still needs a voice test call | Auto: tested() excludes chat (test_booking_by_chat_runs_tools_server_side_and_records_everything); Manual: Agent page |
| TC-P5-28 | Calls | Call record shows actions | A chat with tool uses | Open the call record | Tool uses, booking and ticket listed with links | Manual: Call detail page |
