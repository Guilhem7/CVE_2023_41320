# CVE_2023_41320
POC for CVE 2023 41320 GLPI

Condition: Authenticated User

Vulnerabilities:
 - **SQL Injection** in update clause (be careful :smile:)
 - **Account Takeover** (or privesc on the app)
 - **Remote Code Execution** (in some cases)

This exploit has been tested on **glpi 10.0.9**, it might requires modification in order to work on other version. Mostly both function *extract_val_from_pref* and *set_user_val* might requires some changes. *set_user_val* stores the result of the sql injection in the **realname** field of the **glpi_users** table.

To achieve **RCE** you must allow the upload of extension *.php* (piece of cake when you are an Administrator)
