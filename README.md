# CVE_2023_41320
POC for CVE 2023 41320 on GLPI


| Vulnerability | Condition	| Score *CVSS* |
| ------|-----|------|
| SQL Injection | Authenticated User | 8.1 |

Impact:
 - **SQL Injection** in update clause (be careful :smile:)
 - **Account Takeover** (or privesc on the webapp)
 - **Remote Code Execution** (in some cases, uses the check module to verify)

This exploit has been tested on **glpi 10.0.9**, it might requires modification in order to work on other version. Mostly both function *extract_val_from_pref* and *set_user_val* might requires some changes. *set_user_val* stores the result of the sql injection in the **realname** field of the **glpi_users** table.

To achieve **RCE** you must allow the upload of extension *.php* (piece of cake when you are an Administrator)


Report link:
[Huntr report](https://huntr.com/bounties/77c672dd-319f-4b48-a704-dcffb4d5689a/)

> **_NOTE:_**  Thanks to GLPI for the quick answer and the version patched [here](https://github.com/glpi-project/glpi/tree/10.0.10)
