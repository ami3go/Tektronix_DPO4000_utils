*** Comments ***
Run the A25 headless runner from Robot Framework.

    robot --exclude hardware examples/robot_framework/      # offline validation only
    DPO4000_RESOURCE=USB0::...::INSTR robot examples/robot_framework/

Exit codes 5 (RULE_FAILED) and 6 (RULE_INVALID) mean the DUT failed its acceptance rules.
Any other non-zero code is an infrastructure, recipe or export error.


*** Settings ***
Library             Process
Library             OperatingSystem


*** Variables ***
${RESOURCE}         %{DPO4000_RESOURCE=}
${RECIPE}           ${CURDIR}${/}..${/}a15_recipe_example.json
${RULES}            ${CURDIR}${/}..${/}a16_rules_example.json
${REPORT}           ${OUTPUT DIR}${/}dpo4000_job_report.json


*** Test Cases ***
Recipe Validates Without Instrument I/O
    ${result}=    Run Process    dpo4000-job    --recipe    ${RECIPE}    --rules    ${RULES}
    ...    --validate-only    --report    ${REPORT}
    Should Be Equal As Integers    ${result.rc}    0    msg=${result.stdout}${result.stderr}
    ${report}=    Load Job Report    ${REPORT}
    Should Be Equal    ${report}[status]    validated

Scope Meets Acceptance Rules
    [Tags]    hardware
    Skip If    not $RESOURCE    DPO4000_RESOURCE is not set
    ${result}=    Run Process    dpo4000-job    --recipe    ${RECIPE}    --rules    ${RULES}
    ...    --resource    ${RESOURCE}    --report    ${REPORT}    --output-format    text
    Log    ${result.stdout}
    ${report}=    Load Job Report    ${REPORT}
    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=dpo4000-job ${report}[status]: ${report}[message]


*** Keywords ***
Load Job Report
    [Arguments]    ${path}
    File Should Exist    ${path}
    ${text}=    Get File    ${path}
    ${report}=    Evaluate    json.loads($text)    modules=json
    RETURN    ${report}
