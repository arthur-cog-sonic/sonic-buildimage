# AAA Klish CLI High-Level Design Document

## 1. Architecture Overview

This document describes the migration of AAA (Authentication, Authorization, and Accounting) CLI commands from Click-based implementation in `sonic-utilities` to Klish-based implementation in `sonic-mgmt-framework`, using the OpenConfig AAA YANG model with transformer-based translation to SONiC's native AAA YANG model.

### 1.1 Three-Layer Klish Architecture

```
+-------------------+     +---------------------+     +--------------------+
|   CLI XML (Klish) | --> | Python Actioner     | --> | REST API (translib)|
|   aaa.xml         |     | sonic_cli_aaa.py    |     |                    |
+-------------------+     +---------------------+     +--------------------+
                                                              |
                                                              v
                                                     +--------------------+
                                                     | Transformer        |
                                                     | xfmr_aaa.go       |
                                                     +--------------------+
                                                              |
                                                              v
                                                     +--------------------+
                                                     | SONiC ConfigDB     |
                                                     | AAA Table          |
                                                     +--------------------+
```

**Layer 1 - XML Definitions** (`aaa.xml`): Defines CLI command syntax, parameters, help strings, and parameter types using Klish XML schema. Maps commands to Python actioner method calls.

**Layer 2 - Python Actioner** (`sonic_cli_aaa.py`): Translates CLI parameters into OpenConfig-compliant REST API requests (PATCH/GET/DELETE). Uses `cli_client.ApiClient()` for REST communication.

**Layer 3 - Go Transformer** (`xfmr_aaa.go`): Bidirectional translation between OpenConfig AAA model and SONiC native AAA model in ConfigDB using a subtree transformer approach.

### 1.2 Show Command Flow

```
CLI (show aaa)
  --> XML (enable-view COMMAND)
  --> Actioner (GET /restconf/data/openconfig-aaa:aaa)
  --> Transformer (DbToYang: reads AAA table, builds OpenConfig response)
  --> Jinja2 Template (show_aaa.j2 formats output)
  --> CLI Output
```

### 1.3 Config Command Flow

```
CLI (aaa authentication failthrough enable)
  --> XML (configure-view COMMAND)
  --> Actioner (PATCH /restconf/data/openconfig-aaa:aaa with body)
  --> Transformer (YangToDb: maps OpenConfig to AAA|authentication|failthrough=True)
  --> ConfigDB Update
```

## 2. Command Mapping Table

| Click Command | Klish Command | OpenConfig Path | SONiC DB Key |
|---|---|---|---|
| `config aaa authentication failthrough enable` | `aaa authentication failthrough enable` | `/openconfig-aaa:aaa/authentication/config/failthrough` | `AAA\|authentication\|failthrough=True` |
| `config aaa authentication failthrough disable` | `aaa authentication failthrough disable` | `/openconfig-aaa:aaa/authentication/config/failthrough` | `AAA\|authentication\|failthrough=False` |
| `config aaa authentication failthrough default` | `aaa authentication failthrough default` | DELETE on failthrough | `AAA\|authentication` (remove failthrough) |
| `config aaa authentication fallback enable` | `aaa authentication fallback enable` | `/openconfig-aaa:aaa/authentication/config/fallback` | `AAA\|authentication\|fallback=True` |
| `config aaa authentication debug enable` | `aaa authentication debug enable` | `/openconfig-aaa:aaa/authentication/config/debug` | `AAA\|authentication\|debug=True` |
| `config aaa authentication login tacacs+ local` | `aaa authentication login tacacs+ local` | `/openconfig-aaa:aaa/authentication/config/authentication-method` | `AAA\|authentication\|login=tacacs+,local` |
| `config aaa authentication login default` | `aaa authentication login default` | DELETE on authentication-method | `AAA\|authentication` (remove login) |
| `config aaa authorization tacacs+ local` | `aaa authorization tacacs+ local` | `/openconfig-aaa:aaa/authorization/config/authorization-method` | `AAA\|authorization\|login=tacacs+,local` |
| `config aaa accounting tacacs+` | `aaa accounting tacacs+` | `/openconfig-aaa:aaa/accounting/config/accounting-method` | `AAA\|accounting\|login=tacacs+` |
| `config aaa accounting disable` | `aaa accounting disable` | DELETE on accounting-method | `AAA\|accounting` (remove login) |
| `show aaa` | `show aaa` | GET `/openconfig-aaa:aaa` | Read all AAA entries |

## 3. Transformer Design

### 3.1 Subtree Transformer Approach

A single subtree transformer (`aaa_subtree_xfmr`) handles the entire `/openconfig-aaa:aaa` tree. This approach is chosen because:

- The OpenConfig AAA model uses separate containers (authentication, authorization, accounting) while SONiC uses a single list (`AAA_LIST`) with a `type` key
- The transformation logic is straightforward but structurally different between models
- A subtree transformer provides full control over the mapping without needing individual field transformers

### 3.2 Authentication Method Transformation

**OpenConfig Model:**
```yang
leaf-list authentication-method {
    type union { type identityref; type string; }
    ordered-by user;
}
```

**SONiC Model:**
```yang
leaf login {
    type string {
        pattern '((ldap|tacacs\+|local|radius|default),)*(ldap|tacacs\+|local|radius|default)';
    }
}
```

**Conversion:**
- YangToDb: `["tacacs+", "local"]` → `"tacacs+,local"`
- DbToYang: `"tacacs+,local"` → `["tacacs+", "local"]`

### 3.3 Boolean Field Mapping

OpenConfig extensions (failthrough, fallback, debug) map directly to SONiC boolean_type fields:
- YangToDb: `true` → `"True"`, `false` → `"False"`
- DbToYang: `"True"` → `true`, `"False"` → `false`

### 3.4 Key Transformation

OpenConfig uses separate containers for each AAA type:
- `/aaa/authentication/config/...` → `AAA|authentication|...`
- `/aaa/authorization/config/...` → `AAA|authorization|...`
- `/aaa/accounting/config/...` → `AAA|accounting|...`

## 4. YANG Annotation

The annotation file (`openconfig-aaa-annot.yang`) registers the subtree transformer at the top-level `/oc-aaa:aaa` container:

```yang
deviation /oc-aaa:aaa {
    deviate add {
        sonic-ext:subtree-transformer "aaa_subtree_xfmr";
    }
}
```

## 5. Files Created

| File | Repository | Purpose |
|---|---|---|
| `models/yang/annotations/openconfig-aaa-annot.yang` | sonic-mgmt-common | YANG annotation for transformer binding |
| `translib/transformer/xfmr_aaa.go` | sonic-mgmt-common | Go subtree transformer implementation |
| `CLI/clitree/cli-xml/aaa.xml` | sonic-mgmt-framework | Klish XML CLI definitions |
| `CLI/actioner/sonic_cli_aaa.py` | sonic-mgmt-framework | Python REST API actioner |
| `CLI/renderer/templates/show_aaa.j2` | sonic-mgmt-framework | Jinja2 show command template |

## 6. Testing

### 6.1 Unit Tests
- Go transformer tests verify bidirectional conversion functions
- Python actioner tests verify REST API construction and error handling

### 6.2 Integration Testing
- VS build verification
- kvmtest validation on virtual DUT
- End-to-end CLI command testing through Klish shell
