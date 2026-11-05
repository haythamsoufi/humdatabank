# FDRS + Unified Reporting: merged endpoint and indicator mapping

Endpoint: `GET /api/v1/upr/overall` (same auth as `/api/v1/upr/data`; code in `plugins/upr/overall_data.py`).

Generated from the local dev database on 2026-11-05. Indicator Bank ids are stable, so the matching below holds on other environments as long as the templates carry the same form items; re-check after template changes.

## Rules

1. **Matching key** is *country + calendar year + Indicator Bank id*. Labels differ between the templates (for example `Number of people volunteering.` in FDRS and `Volunteers` in Unified Reporting), the bank id is the same.
2. **Priority**: `FDRS` (template 21) first. If FDRS has no figure for that country, year and indicator, use `Unified Reporting` (template 33): the **annual report** (period `2024`, round `AR24`) first, then the **mid-year report** (`Jan-Jun 2024`, round `MYR24`).
3. **A figure counts** when the winning source has a number. A source that only says "data not available / not applicable" loses to a source with a number; if no source has a number, the highest-priority flag is kept.
4. **A source is taken whole.** All attributes (Total, Direct, Indirect, male/female age bands) come from the one source that won, so disaggregations from two sources are never mixed.
5. **Only approved country assignments** are read, for both templates.
6. **Data source** column replaces `Source`: `FDRS` or `Unified Reporting`. `Round` shows the exact round (`FDRS24`, `AR24`, `MYR24`) and `submission_id` the exact submission.
7. Everything FDRS does not collect (emergency appeal indicators, bilateral support, funding sources, comments) is passed through from Unified Reporting unchanged; no matching is applied.
8. Year: FDRS period `2024` and Unified Reporting `2024` / `Jan-Jun 2024` all mean calendar year 2024. Mid-year only covers January to June, so it is the last choice.

## Output columns

Same as `/api/v1/upr/data` `data`, with `Source` renamed to `Data source` and `Country Value` replaced by `FDRS Value` and `UPR Value`:

`Round, ISO3, Country, NS, Region, Section, SectionB, Data source, Entity, Attribute, SP/EF, Applicable/Data not available, Indicator, Value, ValueNum, FDRS Value, UPR Value, PNS Value, PNS reported, Year, EA Code, submission_id`

- `Value` / `ValueNum`: the final figure, from the winning source (`Data source`).
- `FDRS Value`: what FDRS reported for the same cell (same indicator and attribute); blank if none.
- `UPR Value`: what Unified Reporting reported for the same cell (annual first, then mid-year); blank if none.

So when both reported, both are visible, and `Value` equals the FDRS one.

Query parameters: `iso3` (alias `country_iso3`), `year`, `section`.

## Summary

| Group | Indicators | Result |
|---|---:|---|
| In **both** FDRS (21) and Unified Reporting (33) | 21 | FDRS wins, Unified Reporting fills gaps |
| **FDRS only** (not in template 33 form) | 9 | `FDRS`; see note on 3 of them below |
| **Unified Reporting only**, fixed form items | 24 | `Unified Reporting` |
| **Unified Reporting only**, country-level "Other indicators" (dynamic) | 165 | `Unified Reporting` |

### Effect on the shared indicators (cells = country x indicator, approved, with a number)

| Year | FDRS has a figure | Unified Reporting has a figure | Both (FDRS used, UR ignored) | Only Unified Reporting (UR used) |
|---|---:|---:|---:|---:|
| 2020 | 1894 | 0 | 0 | 0 |
| 2021 | 2189 | 0 | 0 | 0 |
| 2022 | 2212 | 0 | 0 | 0 |
| 2023 | 2438 | 1497 | 1234 | 263 |
| 2024 | 2442 | 1718 | 1453 | 265 |
| 2025 | 1247 | 1600 | 766 | 834 |
| 2026 | 0 | 475 | 0 | 475 |

FDRS 2025 is still being approved (77 of 192 approved), which is why Unified Reporting fills many 2025 cells. 2026 has no FDRS yet, so mid-year 2026 is used as it comes in. Fixed form items only; indicators reported through dynamic "Other indicators" are matched the same way but not counted here.

## A. In both templates (matched, FDRS first)

| Bank id | Indicator (Indicator Bank) | FDRS item (21) | FDRS section | Unified Reporting item (33) | UR section | Output `Section` |
|---:|---|---|---|---|---|---|
| 612 | Number of people reached with activities to address rising climate risks | `947` Number of people reached with activities to address ris | By thematic areas | `1380` Number of people reached with activities to address ris | Resilience - Climate and environment | Core indicators |
| 613 | Number of people reached with heatwave risk reduction, preparedness or response activities | `948` Number of people reached with heatwave risk reduction,  | By thematic areas | `1381` Number of people reached with heatwave risk reduction,  | Resilience - Climate and environment | Core indicators |
| 618 | Number of people reached with disaster risk reduction | `922` Number of people reached with disaster risk reduction | By thematic areas | `1375` Number of people reached with disaster risk reduction | Response - Disasters and crises | Core indicators |
| 619 | Number of people reached with emergency response and early recovery programmes | `921` Number of people reached with emergency response and ea | By Type of Programme | `1369` Number of people reached with emergency response and ea | Cross Cutting | Core indicators |
| 621 | Number of people reached with livelihoods support | `938` Number of people reached with livelihoods support | By thematic areas | `1378` Number of people reached with livelihoods support | Response - Disasters and crises | Core indicators |
| 622 | Number of people reached with shelter support | `932` Number of people reached with shelter support | By thematic areas | `1379` Number of people reached with shelter support | Response - Disasters and crises | Core indicators |
| 623 | Number of people reached with contextually appropriate health services | `940` Number of people reached with contextually appropriate  | By thematic areas | `1386` Number of people reached with contextually appropriate  | Resilience - Health and wellbeing | Core indicators |
| 624 | Number of people reached with contextually appropriate water, sanitation and hygiene services | `945` Number of people reached with contextually appropriate  | By thematic areas | `1387` Number of people reached with contextually appropriate  | Resilience - Health and wellbeing | Core indicators |
| 625 | Number of people trained in first aid | `930` Number of people trained in first aid | Blood and First Aid Activities | `1388` Number of people trained in first aid | Resilience - Health and wellbeing | Core indicators |
| 626 | Number of people donating blood | `920` Number of people donating blood | Blood and First Aid Activities | `1389` Number of people donating blood | Resilience - Health and wellbeing | Core indicators |
| 627 | Number of people reached with psychosocial and mental health services | `942` Number of people reached with psychosocial and mental h | By thematic areas | `1390` Number of people reached with psychosocial and mental h | Resilience - Health and wellbeing | Core indicators |
| 628 | Number of people reached with immunization services | `944` Number of people reached with immunization services | By thematic areas | `1391` Number of people reached with immunization services | Resilience - Health and wellbeing | Core indicators |
| 629 | Number of migrants and displaced persons reached with services for assistance and protection | `946` Number of migrants and displaced persons reached with s | By thematic areas | `1392` Number of migrants and displaced persons reached with s | Resilience - Migration and displacement | Core indicators |
| 633 | Number of people reached by the National Society's educational programmes | `951` Number of people reached by the National Society's educ | By thematic areas | `1396` Number of people reached by the National Society's educ | Respect - Values, power and inclusion | Core indicators |
| 635 | Number of people reached by protection, gender and inclusion programming | `950` Number of people reached by protection, gender and incl | By thematic areas | `1398` Number of people reached by protection, gender and incl | Respect - Values, power and inclusion | Core indicators |
| 723 | Number of National Society Local Units | `925` Number of National Society Local Units | Local Units and Branches | `1372` Local Units | Key Data | NS Data |
| 724 | Number of people volunteering | `916` Number of people volunteering | National Society Volunteers | `1370` Volunteers | Key Data | NS Data |
| 727 | Number of paid staff | `917` Number of paid staff | National Society Staff | `1371` Staff | Key Data | NS Data |
| 734 | Total expenditure of the National Society | `1531` Expenditure (CHF) | National Society Financial Data | `1404` National Society [assignment_year] Expenditure (CHF) | Funding | Funding |
| 754 | Number of people reached with long-term services and programmes | `931` Number of people reached with long-term services and pr | By Type of Programme | `1368` Number of people reached with long-term services and pr | Cross Cutting | Core indicators |
| 1117 | Number of National Society branches | `915` Number of National Society branches | Local Units and Branches | `1373` Branches | Key Data | NS Data |

## B. FDRS only (no fixed item in template 33)

| Bank id | Indicator | FDRS item (21) | FDRS section | Also country-level in UR "Other indicators" | Output `Section` / `Indicator` |
|---:|---|---|---|---|---|
| 722 | Number of people on the National Society Governing Board | `914` Number of people on the National Society Governing Boar | Governing Board | no | Core indicators |
| 725 | Number of volunteers covered by accident insurance | `926` Number of volunteers covered by accident insurance | National Society Volunteers | yes, 14 approved rows (matched, FDRS first) | Core indicators |
| 726 | Number of volunteer deaths on duty | `935` Number of volunteer deaths on duty | National Society Volunteers | yes, 5 approved rows (matched, FDRS first) | Core indicators |
| 728 | Number of paid staff covered by accident insurance | `927` Number of paid staff covered by accident insurance | National Society Staff | no | Core indicators |
| 729 | Number of staff deaths on duty | `936` Number of staff deaths on duty | National Society Staff | no | Core indicators |
| 733 | Total income of the National Society | `1530` Funding (CHF) | National Society Financial Data | no | Funding / Funding |
| 765 | Number of people reached - Cash Transfer Programming | `949` Number of people reached - Cash Transfer Programming | By thematic areas | yes, 16 approved rows (matched, FDRS first) | Core indicators |
| 1131 | Total income of the National Society. (reporting currency) | `939` Funding | National Society Financial Data | no | Funding / Funding (reporting currency) |
| 1132 | Total expenditure of the National Society. (reporting currency) | `941` Expenditure | National Society Financial Data | no | Funding / Expenditure (reporting currency) |

Notes:

- **733 / 1131 / 1132 (total income)**: FDRS reports total NS income as a single figure. Unified Reporting's `Funding` is a matrix by funding source (IFRC Secretariat, PNSs, ...), a different measure, so it is not merged and the two coexist. Only **734 Expenditure (CHF)** is the same indicator in both.
- **725, 726, 765**: not fixed items in template 33, but some countries report them as country-level "Other indicators" (dynamic). Those rows are matched with FDRS on the bank id, FDRS first.

## C. Unified Reporting only (fixed form items)

| Bank id | Indicator | UR item (33) | UR section | Type |
|---:|---|---|---|---|
| 614 | Number of people reached with activities to address environmental problems | `1382` Number of people reached with activities to address env | Resilience - Climate and environment | number |
| 615 | National Society implements nature-based solutions (including those with a particular focus on the planting of trees and mangroves) | `1383` National Society implements nature-based solutions (inc | Resilience - Climate and environment | yesno |
| 616 | National Society implements environmental or climate campaigns focused on behaviour change, plastic reduction, clean-ups or reducing GHG emissions | `1384` National Society implements environmental or climate ca | Resilience - Climate and environment | yesno |
| 620 | Percentage of assistance delivered using cash and vouchers | `1377` Percentage of assistance delivered using cash and vouch | Response - Disasters and crises | percentage |
| 630 | Number of Humanitarian Service Points (HSPs) providing assistance and/or protection to people on the move along migration routes | `1393` Number of Humanitarian Service Points (HSPs) providing  | Resilience - Migration and displacement | number |
| 631 | National Society has undertaken any advocacy, dialogues, educational or communication initiatives to change the legal, policy, or operational environment to better assist and protect people on the move | `1394` National Society has undertaken any advocacy, dialogues | Resilience - Migration and displacement | yesno |
| 636 | National Society has a Protection from Sexual Exploitation and Abuse (PSEA) policy to enforce prevention and support survivors | `1415` National Society has a Protection from Sexual Exploitat | Accountability and agility | yesno |
| 637 | National Society has a Protection from Sexual Exploitation and Abuse (PSEA) Action Plan to enforce prevention and support survivors | `1416` National Society has a Protection from Sexual Exploitat | Accountability and agility | yesno |
| 638 | National Society has a Community Engagement and Accountability policy, strategy or plan | `1400` National Society has a Community Engagement and Account | Respect - Values, power and inclusion | yesno |
| 640 | Number of government-led coordination platforms the National Society is part of | `1401` Number of government-led coordination platforms the Nat | Strategic and operational coordination | number |
| 641 | Number of formal interagency/international coordination platforms the IFRC network is part of | `1402` Number of formal interagency/international coordination | Strategic and operational coordination | number |
| 642 | National Society has developed and/or implemented a strategy for strengthening their auxiliary role | `1408` National Society has developed and/or implemented a str | National Society development | yesno |
| 643 | There is a National Society Development plan in place | `1409` There is a National Society Development plan in place | National Society development | yesno |
| 644 | National Society has created and implemented youth engagement strategies | `1410` National Society has created and implemented youth enga | National Society development | yesno |
| 646 | National Society participates in IFRC-led campaigns | `1412` National Society participates in IFRC-led campaigns | Humanitarian diplomacy and communication | yesno |
| 647 | National Society has a domestic advocacy strategy developed aligning, at least in part, with global IFRC advocacy strategies | `1413` National Society has a domestic advocacy strategy devel | Humanitarian diplomacy and communication | yesno |
| 649 | National Society is implementing a digital transformation roadmap in line with the IFRC strategy | `1418` National Society is implementing a digital transformati | Accountability and agility | yesno |
| 650 | National Society has a functioning data management system that informs decision making and supports monitoring and reporting on the impact and evidence of its actions | `1419` National Society has a functioning data management syst | Accountability and agility | yesno |
| 709 | National Society has a functioning community feedback mechanism in place for all its work | `1420` National Society has a functioning community feedback m | Respect - Values, power and inclusion | yesno |
| 711 | National Society has a safe and accessible mechanism (such as the IFRC Integrity Line) in place to report integrity concerns, misconduct and breaches of rules and policies | `1423` National Society has a safe and accessible mechanism (s | Accountability and agility | yesno |
| 1126 | National Society has conducted migration and displacement needs assessment | `1395` National Society has conducted migration and displaceme | Resilience - Migration and displacement | yesno |
| 1128 | Number of staff and volunteers trained on the Fundamental Principles of the International Red Cross and Red Crescent Movement | `1422` Number of staff and volunteers trained on the Fundament | National Society development | number |
| 1129 | National Society has safe and inclusive referral pathways to support survivors of violence to access services | `1399` National Society has safe and inclusive referral pathwa | Respect - Values, power and inclusion | yesno |
| 1130 | The National Society has an official branch development framework, model or guidance that defines the expected role and standards of branches | `1421` The National Society has an official branch development | National Society development | yesno |

## D. Unified Reporting only, country-level "Other indicators" (dynamic)

Indicators added to a Unified Report outside the fixed form (no repeat instance / emergency appeal). Approved rows across all rounds. Indicators that FDRS also covers (matched in A and B) are not repeated here.

<details><summary>Show 165 indicators</summary>

| Bank id | Indicator | Approved country-level rows |
|---:|---|---:|
| 592 | National Society has received IFRC Network’s support to adapt to longer-term impacts of climate change | 1686 |
| 648 | National Society has strengthened its integrity and reputational risk mechanism | 1622 |
| 645 | National Society covers health, accident and death compensation for all of its volunteers | 1566 |
| 632 | National Society has undertaken any data collection, research, analysis or other information management initia | 1237 |
| 639 | Percentage of people surveyed who report receiving useful and actionable information | 932 |
| 634 | Number of people whose access to education is facilitated through National Society's programming | 776 |
| 1111 | National Society is engaged in Early Warning and Anticipatory Action | 531 |
| 425 | National Society is part of its national government’s disaster response management (DRM) plans | 469 |
| 1114 | The National Society has a risk management framework in place | 440 |
| 914 | Number of people who received food items through National Society response | 299 |
| 310 | Number of trees planted for climate change adaptation, mitigation and/or to reduce disaster risk | 292 |
| 1112 | The National Society generates more than 50% of its annual income domestically with sustainable core cost reco | 276 |
| 1109 | Number of people reached by public campaigns involving clean-up, recycling or urban greening | 253 |
| 1113 | Number of strategic partnership the National Society is engaged in | 250 |
| 1110 | Number of people reached by environmental awareness and education activities in schools | 218 |
| 1094 | National Society has undertaken any other activities to strengthen its capacity to assist and protect people o | 140 |
| 330 | Number of people reached through humanitarian service points (migrants, internally displaced persons and host  | 84 |
| 334 | Number of people reached with restoring family links (RFL) services | 81 |
| 187 | Number of staff, volunteers and leadership trained on community engagement and accountability | 72 |
| 768 | Number of people on the move along migration routes who are provided with humanitarian services (assistance, p | 71 |
| 193 | Number of National Society staff and volunteers trained in disaster risk reduction | 70 |
| 770 | Number of people in host communities along migration routes who are provided with humanitarian services (assis | 70 |
| 1115 | Number of people who have returned to the country and have been supported with immediate assistance and protec | 69 |
| 774 | National Society has undertaken any coordination, collaboration or cooperative activities to better assist and | 66 |
| 788 | Number of people covered with hygiene promotion activities | 61 |
| 496 | National Society uses a Federation-wide approach for planning, monitoring and reporting the impact of the IFRC | 56 |
| 36 | Number of sanitation facilities constructed or rehabilitated | 42 |
| 551 | National Society reports that it has a homogeneous system that applies to the entire organisation, either thei | 42 |
| 573 | National Society's governing board includes youth members and other under-represented groups | 42 |
| 131 | Number of people trained on implementing the PGI Minimum Standards | 41 |
| 495 | National Society has a membership coordination mechanism is in place | 34 |
| 114 | National Society implements cash voucher assistance programmes | 30 |
| 706 | National Society has submitted an annual externally audited financial statement to the IFRC | 30 |
| 430 | National Society has an active coordination mechanism for operations | 29 |
| 28 | Number of people who have been provided with an improved protected source of drinking water | 28 |
| 521 | National Society implements programs to support migrants and/or displaced persons | 28 |
| 544 | National Society has a digital transformation strategy | 28 |
| 191 | Number of people reached by disaster risk reduction public awareness messaging and public education campaigns  | 27 |
| 830 | Number of staff and volunteers trained in PGI including referrals | 26 |
| 794 | Number of target population registered and trained as National Society health and/or WASH volunteers | 25 |
| 909 | Number of organized training sessions for staff and volunteers per year | 24 |
| 974 | Number of people received personal hygiene kit which include menstrual hygiene management (MHM) | 23 |
| 1027 | Number of people reached by National Society’s community health promotion | 22 |
| 392 | Number of community disaster response teams (CDRT) trained | 20 |
| 432 | National Society has National Disaster Response teams trained and systems in place for their management | 20 |
| 1095 | Number of litres of safe water distributed | 20 |
| 137 | Number of National Society’s Programmes that have completed the IFRC Child Safeguarding Risk Analysis | 19 |
| 434 | Number of branches supported through "Red Ready" Initiative to be ready to respond to disasters | 19 |
| 33 | Number of people reached with effective water treatment materials and promotion | 18 |
| 996 | Number of people transported by National Society’s ambulances / medical transport to health facilities | 18 |
| 336 | Number of people who have been reunited with their families through restoring family links (RFL) services | 15 |
| 582 | National Society supports crisis and disaster response and recovery outside its own territory, with finance, p | 15 |
| 606 | National Society is able to deliver scalable, timely and accountable cash and voucher assistance | 15 |
| 611 | National Society has community engagement and accountability integrated in its strategy or plan with clear goa | 15 |
| 927 | Number of persons reached with awareness-raising sessions focused on promotion of positive mental health and p | 15 |
| 1052 | Number of people trained in epidemic control | 15 |
| 25 | Percentage of households that have access to sufficient safe water which meets Sphere and WHO standards in ter | 14 |
| 100 | Number of (temporary) safe spaces established or operated by the National Society for the purpose of learning, | 14 |
| 168 | National Society has a safeguarding focal person | 14 |
| 192 | Number of communities that have developed a risk informed community plan of action with National Society's sup | 14 |
| 249 | Number of people receiving any form of education support provided by the National Society | 14 |
| 294 | Number of people provided or supported with functional literacy or numeracy classes or any other form of suppo | 14 |
| 326 | Number of people reached by social cohesion activities to improve relations between migrants , internally disp | 14 |
| 333 | Number of staff and volunteers trained in Migration & Displacement | 14 |
| 473 | National Society adopts greening practices to improve the environmental sustainability of its operations and p | 14 |
| 527 | Number of schools or other educational spaces in which National Society's staff or volunteers carry out educat | 14 |
| 529 | National Society has a signed agreement with education authority or other relevant authorities or stakeholders | 14 |
| 601 | National Society has clear or strengthened auxiliary role in situations of migration and displacement | 14 |
| 762 | Number of people reached - Migration | 14 |
| 878 | National Society has prepositioned NFIs for harsh winter conditions | 14 |
| 1039 | Number of people reached with vector control in emergencies | 14 |
| 134 | Number of referrals made for survivors of a protection violation, via a common referral pathway | 13 |
| 553 | Number of National Society personnel (staff and volunteers) receiving digital and/or data training | 12 |
| 22 | Number of communities / sites reached with WASH actions in emergency response | 10 |
| 80 | Number of people provided with handwashing facilities | 10 |
| 154 | Number of safe and accessible water points for cooking and drinking water which are culturally appropriate, co | 10 |
| 186 | Percentage of people surveyed who report they know how to provide feedback about the organisation/programme/op | 10 |
| 448 | Number of people supported to start or improve their income generation activities | 10 |
| 528 | Number of schools or other educational spaces in which National Society's programming takes place | 10 |
| 955 | Number of active trained volunteers community-based health workers (CBHWs/CHWs) / community volunteers / commu | 10 |
| 1053 | Number of people reached with epidemic-related health promotion activities | 10 |
| 129 | Number of sectoral or PGI assessments conducted using the PGI Minimum Standards | 9 |
| 138 | Number of children participating in child-friendly consultations to help design, implement, and monitor any pr | 9 |
| 148 | Number of people referred to survivor-centred SGBV-dedicated services | 9 |
| 238 | Number of people who have completed training in improved agricultural / food production risk management practi | 9 |
| 319 | Number of water pumps or other infrastructure using solar power or other renewable energy | 9 |
| 467 | Number of people reached by epidemic and pandemic preparedness and response activities | 9 |
| 506 | Diversity of National Society’s staff at senior level | 9 |
| 602 | Percentage of humanitarian assistance provided in-kind | 9 |
| 610 | Number of community engagement and accountability coordination forums attended | 9 |
| 804 | Number of target population provided by  with access to safely managed drinking water services or an improved  | 9 |
| 806 | Percentage of target population with access to a handwashing facility with soap and water on premises | 9 |
| 924 | Number of people who have received psychological support delivered by National Society trained staff/volunteer | 9 |
| 932 | Number of people reached by all National Society social care services (including both care in the home or in i | 9 |
| 938 | Number of people reached by National Society health promotion / awareness activities for the prevention and co | 9 |
| 941 | Number of people reached by National Society health promotion / awareness messages in social / mass media or l | 9 |
| 943 | Number of people reached with health promotion activities related to non-communicable diseases (NCDs) manageme | 9 |
| 946 | Number of people in migrant programmes reached with contextually appropriate National Society services aimed a | 9 |
| 947 | Number of people included in National Society’s programmes in support of migrants who were referred by the pro | 9 |
| 970 | Number of people reached by the National Society with solid waste disposal service | 9 |
| 987 | Number of people reached with search and rescue activities conducted | 9 |
| 543 | National Society includes innovation in plans and budgetary allocations | 8 |
| 1086 | National Society is running, or has presence in, reception centres for migrants | 6 |
| 1101 | Number of people provided with unconditional cash assistance | 6 |
| 12 | Number of communities / sites provided with shelter-related response | 5 |
| 30 | Average number of litres of safe water distributed per person per day | 5 |
| 45 | Percentage of households who report being able to meet the basic needs of their households, according to their | 5 |
| 46 | Percentage of households provided with CVA assistance that have not sold any livelihood assets as a coping str | 5 |
| 50 | Expenditure as conditional cash assistance | 5 |
| 63 | Number of targeted sites for which debris removal has been completed | 5 |
| 82 | Number of handwashing facilities constructed or rehabilitated | 5 |
| 101 | Number of people with access to (temporary) safe spaces established or operated by the National Society for th | 5 |
| 112 | Number of National Society branches with education programming | 5 |
| 132 | Percentage of operations which link to an existing referral pathway | 5 |
| 164 | Number of National Society staff and volunteers trained on prevention and protection of sexual exploitation an | 5 |
| 174 | Number of methods used to enable communities to participate in planning and managing services, programmes and  | 5 |
| 201 | Number of towns or cities supported to adapt to longer-term impacts of climate change, including sea level ris | 5 |
| 215 | Percentage of surveyed people whose households received cash transfers / vouchers are satisfied with the amoun | 5 |
| 220 | Number of people reached with essential on-farm and off-farm inputs/materials/tools for agricultural/food prod | 5 |
| 239 | Number of people who have completed training or awareness-raising sessions on nutrition-sensitive practices | 5 |
| 256 | Number of teachers or and other education personnel (incl. volunteer facilitators) trained by the National Soc | 5 |
| 261 | Number of teachers or other education personnel trained on first aid, health, water, sanitation or hygiene rel | 5 |
| 293 | Number of people provided or supported with formal or informal technical, vocational or professional education | 5 |
| 307 | Number of households provided with a sustainable household energy solution | 5 |
| 331 | Number of specific advocacy representations made towards meeting the needs of migrants | 5 |
| 547 | Number of specific innovation teams or hubs operating in the National Society | 5 |
| 548 | Number of innovations developed at the branch level by local volunteers or community members that are financia | 5 |
| 605 | Number of cash programmes that provide "cash-plus" assistance to affected populations | 5 |
| 663 | Number of opportunities for communities to participate in planning and managing the programme/operation (e.g., | 5 |
| 693 | Number of National Society community health workers CHW or community health volunteers per 100,000 people | 5 |
| 784 | Number of people provided with access to safely managed drinking water services or an improved drinking water  | 5 |
| 798 | Number of people reached with WASH actions in emergency response | 5 |
| 823 | Number of national and local plans, legal and regulatory frameworks with references to DRR and Early Warning a | 5 |
| 828 | Number of communities covered regularly with mobile health units or health outreach activities | 5 |
| 868 | Number of social workers engaged | 5 |
| 888 | Number of active ageing services established | 5 |
| 890 | Number of community health promotion volunteers trained and engaged in active ageing | 5 |
| 891 | Number of social workers, volunteers and staff who participated in psychological first aid training, psycho-so | 5 |
| 895 | Number of mobile health service units functional to provide quality primary health care | 5 |
| 899 | Percentage of [name of service] staff and volunteers trained on prevention of sexual exploitation and abuse (P | 5 |
| 926 | Number of people who were engaged in focused psychosocial activities delivered by the National Society whose m | 5 |
| 959 | Number of pregnancies where care (PNC or ANC) is delivered by RC supported/trained/funded midwife / auxiliary  | 5 |
| 985 | Number of active volunteers trained in first aid | 5 |
| 997 | Number of ambulances operated by the National Society to provide medical transportation and pre-hospital care | 5 |
| 1000 | Number of people reached through primary health care / outreach services / mobile units / clinics operated by  | 5 |
| 1001 | Number of consultations through primary health care rooms / outreach services / mobile units / clinics operate | 5 |
| 1032 | Number of people receiving insecticide treated net (ITN) distributed by the National Society in non-emergency  | 5 |
| 1038 | Number of people receiving insecticide treated nets (ITN) distributed | 5 |
| 1068 | Percentage of surveyed people who feel the organisation/programme/operation has communicated well about plans  | 5 |
| 1069 | Percentage of people surveyed who feel treated with respect by the organisation's/programme's/operation's staf | 5 |
| 1102 | Number of people provided with voucher assistance | 5 |
| 1121 | National Society has a Protection, Gender and Inclusion (PGI) focal person | 5 |
| 510 | National Society has strengthened its integrity and reputational risk mechanisms | 4 |
| 921 | Number of volunteers and staff trained in livelihoods | 4 |
| 925 | Number of people who received individualized psychosocial support, including Psychological First Aid (PFA), by | 4 |
| 930 | Number of people who receive mental health and psychosocial services in emergency situation | 4 |
| 1012 | Number of childbirths attended by a skilled health worker in a health facility operated by the National Societ | 4 |
| 718 | National Society has revised statutes according to Guidance for National Society Statutes | 2 |
| 236 | Number of people reached with messages on good nutrition and / or food preparation | 1 |
| 537 | National Society has its data on “people reached” disaggregated by sex, age and disability | 1 |
| 581 | National Society is engaged in structured preparedness and capacity building processes | 1 |
| 51 | Expenditure in CHF as vouchers | 0 |
| 116 | National Society has a health or WASH strategy for public health in emergencies | 0 |
| 978 | National Society is able to respond to outbreaks with WASH and/or treatment workforce (volunteers, staff) and  | 0 |
| 1097 | Number of people provided with conditional cash assistance | 0 |

</details>

Dynamic rows tied to an emergency appeal (`Emergency N` sections, one per appeal) are always passed through as Unified Reporting and are never replaced by FDRS, even when the bank id is shared with a FDRS indicator, because they describe one appeal, not the country total.

## Template items that are not merged

| Template | Item | Why |
|---|---|---|
| 21 | Key Documents (Annual Report, Strategic Plan, Audited/Unaudited Financial Statement) | Documents, not data |
| 21 | Reporting currency, Financial reporting start/end date, Sex of president, Sex of Secretary General | Questions with no Unified Reporting counterpart |
| 21 | `Income Sources` matrix (943) | No Indicator Bank id. Unified Reporting `Funding` matrix (1403) is a different layout (funding by source, with IFRC Secretariat and PNS columns) |
| 21 | `National Societies to which / from which support was given` matrices (919, 929) | Network support between National Societies. Unified Reporting `Received Support` (1407) is bilateral support by SP/EF area, so the two are not merged |
| 33 | Funding matrix (1403), SP/EF breakdown (1405), Received Support (1407), Emergency appeals, Comments | Unified Reporting only; passed through |


