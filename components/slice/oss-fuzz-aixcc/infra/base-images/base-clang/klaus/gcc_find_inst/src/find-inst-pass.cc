#include <assert.h>
#include "gcc-plugin.h"
#include "tree.h"
#include "gimple.h"
#include "gimple-iterator.h"
#include "context.h"
#include "debug.h"
#include "gimple-walk.h"
#include "plugin-version.h"
#include "tree-pass.h"

/* This plugin, being under the same license as GCC, satisfies the
   "GPL-compatible Software" definition in the GCC RUNTIME LIBRARY
   EXCEPTION, so it can be part of an "Eligible" "Compilation
   Process".  */
int plugin_is_GPL_compatible = 1;

namespace {

#define MAX_STRUCT_NAME 0x100
#define MAX_FILE_NAME 0x300
#define MAP_BLOCK 0x10
// #define DEBUG
#ifdef DEBUG
#define gcc_log(fmt, ...) fprintf(stderr, fmt, ##__VA_ARGS__)
#else
#define gcc_log(fmt, ...)
#endif

struct st {
    struct st* next;
    int field;
    char name[];
};

enum INST_STATE {
    PRE_INST,
    POST_INST,
    PROP_INST,
    VAL_INST,
    COND_INST,
};

struct tree_cb {
    struct walk_stmt_info info;
    unsigned int flag;
    unsigned long long data;
};

struct cond {
    struct cond* next;
    char* funcname;
    char* filename;
    int line;
    unsigned idx;
    struct st st;
};

struct prop_list {
    struct prop_list* next;
    char* funcname;
    char* filename;
    int line;
    unsigned idx;
    struct st* pre;
    struct st* post;
};

struct cond* cond_list = NULL;
struct prop_list* p_list = NULL;
static unsigned int prop_idx = 1;

static struct cond* lookup_cond(struct cond* c, const char* name, int field) {
    struct cond* cond = c ? c : cond_list;
    while (cond) {
        if (!strcmp(cond->st.name, name) && cond->st.field == field) {
            return cond;
        }
        cond = cond->next;
    }
    return cond;
}

static struct st* lookup_struct(struct st* s, const char* name, int field) {
    struct st* cur = s;
    while (cur) {
        if (!strcmp(name, cur->name) && cur->field == field) {
            return cur;
        }
        cur = cur->next;
    }
    return cur;
}

static unsigned lookup_prop_st(const char* name, int field) {
    struct prop_list* p = p_list;
    while (p) {
        if (lookup_struct(p->pre, name, field)) {
            return (p->idx << 8 | 1);
        }
        if (lookup_struct(p->post, name, field)) {
            return (p->idx << 8 | 2);
        }
        p = p->next;
    }
    return 0;
}

static prop_list* lookup_prop(const char* file, int line) {
    if (file == NULL)
        return 0;

    struct prop_list* p = p_list;
    while (p) {
        if (!strcmp(p->filename, file) && p->line == line) {
            return p;
        }
        p = p->next;
    }
    return NULL;
}

void load_cond_file() {
    char* cond_file = getenv("COND_FILE");
    if (cond_file == NULL) {
        printf("COND_FILE is NULL\n");
        return;
    }

    FILE* fp = fopen(cond_file, "r");
    if (fp == NULL) {
        printf("Cannot open %s\n", cond_file);
        return;
    }

    char buf[MAX_STRUCT_NAME];
    char filename[MAX_FILE_NAME];
    char func[MAX_FILE_NAME];

    int field, line;
    while (1) {
        if (fscanf(fp, "%s %d %s %d %s\n", buf, &field, filename, &line,
                   func) != 5) {
            break;
        }

        if (strlen(buf) == 0 || strlen(func) == 0) {
            break;
        }

        gcc_log("init the pair %s %d %s\n", buf, field, func);

        if (lookup_cond(NULL, buf, field)) {
            continue;
        }

        gcc_log("adding object %s:%d at %s:%d\n", buf, field, filename, line);
        // insert the pair
        struct cond* c = (struct cond*)xmalloc(sizeof(*c) + strlen(buf) + 1);
        static unsigned int cond_idx = 1;
        c->funcname = xstrdup(func);
        c->filename = xstrdup(filename);
        c->line = line;
        c->idx = cond_idx++;
        c->st.field = field;
        strcpy(c->st.name, buf);
        c->next = cond_list;
        cond_list = c;
    }
    fclose(fp);
}

void read_struct(FILE* fp, prop_list* p, int is_pre) {
    // load pre
    char struct_name[MAX_STRUCT_NAME];
    int field;
    while (1) {
        memset(struct_name, 0, sizeof(struct_name));
        if (fscanf(fp, "%s %d", struct_name, &field) != 2) {
            break;
        }

        // a struct name never starts with -
        if (strlen(struct_name) == 0 || struct_name[0] == '-') {
            break;
        }

        gcc_log("loading pre %s %d\n", struct_name, field);
        if (lookup_struct(p->pre, struct_name, field)) {
            continue;
        }

        struct st* s =
            (struct st*)xmalloc(sizeof(*s) + strlen(struct_name) + 1);
        s->field = field;
        strcpy(s->name, struct_name);
        if (is_pre) {
            s->next = p->pre;
            p->pre = s;
        } else {
            s->next = p->post;
            p->post = s;
        }
    }
}

void load_prop_file() {
    char* prop_file = getenv("PROP_FILE");
    if (prop_file == NULL) {
        printf("PROP_FILE is NULL\n");
        return;
    }

    FILE* fp = fopen(prop_file, "r");
    if (fp == NULL) {
        printf("Cannot open %s\n", prop_file);
        return;
    }

    gcc_log("loading prop file\n");

    char filename[MAX_FILE_NAME];
    char func[MAX_FILE_NAME];
    int line;

    while (1) {
        if (fscanf(fp, "%s %d %s", filename, &line, func) != 3) {
            break;
        }

        if (strlen(filename) == 0 && strlen(func) == 0) {
            break;
        }

        gcc_log("adding new set %s %d %s\n", filename, line, func);
        struct prop_list* p = lookup_prop(filename, line);

        if (p == NULL) {
            p = (struct prop_list*)xmalloc(sizeof(*p));
            p->funcname = xstrdup(func);
            p->filename = xstrdup(filename);
            p->line = line;
            p->idx = prop_idx++;
            p->pre = p->post = NULL;
            p->next = p_list;
            p_list = p;
        }

        // load pre
        read_struct(fp, p, 1);

        // load post
        read_struct(fp, p, 0);
    }
    gcc_log("done with load prop\n\n");
    fclose(fp);
}

void init_structs() {
    load_cond_file();
    load_prop_file();
}

tree process_tree(tree t, void* cb) {
    if (t == NULL_TREE)
        return NULL;

#ifdef DEBUG
    static int id = 0;
    gcc_log("\n\nid : %d ", id++);
#endif

    if (TREE_CODE(t) == COMPONENT_REF) {
        tree op0 = TREE_OPERAND(t, 0);
        tree op1 = TREE_OPERAND(t, 1);

        const char *type_name, *field_name;
        int field_offset = -1;
        tree type = TREE_TYPE(op0);
        struct tree_cb* tree_cb = (struct tree_cb*)(cb);
        struct cond* cond;
        if (TREE_CODE(type) != RECORD_TYPE) {
            goto out;
        }
        assert(TREE_CODE(type) == RECORD_TYPE);
        type_name = field_name = NULL;

        if (TYPE_IDENTIFIER(type) != NULL_TREE) {
            type_name = IDENTIFIER_POINTER(TYPE_IDENTIFIER(type));
            gcc_log("got typename: %s\n", type_name);
        }

        if (type_name == NULL) {
            goto out;
        }

        assert(TREE_CODE(op1) == FIELD_DECL);
        if (DECL_FIELD_OFFSET(op1)) {
            gcc_log("offset 1 %d offset 2 %d\n",
                    TREE_INT_CST_LOW(DECL_FIELD_OFFSET(op1)),
                    TREE_INT_CST_LOW(DECL_FIELD_BIT_OFFSET(op1)));
            field_offset = TREE_INT_CST_LOW(DECL_FIELD_OFFSET(op1));
            field_offset += TREE_INT_CST_LOW(DECL_FIELD_BIT_OFFSET(op1)) / 8;
        }

        cond = lookup_cond(NULL, type_name, field_offset);
        if (cond == NULL) {
            // check if pre or post inst
            gcc_log("didn't found cond, looking for prop %s %d\n", type_name,
                    field_offset);
            unsigned res = lookup_prop_st(type_name, field_offset);
            gcc_log("got res %d\n", res);
            if (res) {
                tree_cb->flag = PROP_INST;
                tree_cb->data = (unsigned long long)res;
                return t;
            }
        } else {
            gcc_log("found cond pair: %s:%d\n", type_name, field_offset);
            tree_cb->flag = COND_INST;

            if (INTEGRAL_TYPE_P(TREE_TYPE(op1))) {
                gcc_log("this is integer at %s %d\n", EXPR_FILENAME(t),
                        EXPR_LINENO(t));
                gcc_log("cond location : %s:%d\n", cond->filename, cond->line);
                if (EXPR_FILENAME(t) != NULL &&
                    !strcmp(cond->filename, EXPR_FILENAME(t)) &&
                    cond->line == EXPR_LINENO(t)) {
                    gcc_log("got value feedback point\n");
                    tree_cb->flag = VAL_INST;
                    tree_cb->data = (unsigned long long)cond->idx;
                }
            }
            return t;
        }
    }

out:
    return process_tree(TREE_TYPE(t), cb);
}

tree find_st(tree* t, int* walk_subtrees, void* cb_data) {
    *walk_subtrees = 1;
    if (!cond_list && !p_list) {
        gcc_log("cond list or p list is not inited\n");
        return NULL;
    }
    return process_tree(*t, cb_data);
}

static const struct pass_data find_inst_data = {

    .type = GIMPLE_PASS,
    .name = "gccfindinst",
    .optinfo_flags = OPTGROUP_NONE,
    .tv_id = TV_NONE,
    .properties_required = PROP_cfg,
    .properties_provided = 0,
    .properties_destroyed = 0,
    .todo_flags_start = 0,
    .todo_flags_finish = 0,

};

void output_to_file(const char* type, gimple* stmt, function* fun) {
    static char* output_file = getenv("OUTPUT_FILE");
    if (output_file == NULL) {
        FATAL("Unable to read environment variable OUTPUT_FILE");
        return;
    }
    char cwd[PATH_MAX];
    if (getcwd(cwd, sizeof(cwd)) == NULL) {
        FATAL("getcwd() failed");
        return;
    }

    FILE* fp = fopen(output_file, "a");  // append to file
    if (fp == NULL) {
        FATAL("Cannot open %s", output_file);
        return;
    }

    const char* funname = "unknown";
    tree fndecl = cfun->decl;
    if (DECL_NAME(fndecl)) {
        funname = IDENTIFIER_POINTER(DECL_NAME(fndecl));
    }

    fprintf(fp, "%s:%s/%s:%s:%d\n", type, cwd, gimple_filename(stmt), funname,
            gimple_lineno(stmt));
    fclose(fp);
}

unsigned int find_pass(function* fun) {
    if ((flag_sanitize_coverage & SANITIZE_COV_TRACE_PC) == 0) {
        return 0;
    }

    basic_block bb;

    FOR_EACH_BB_FN(bb, fun) {
        gimple_stmt_iterator gsi = gsi_start_nondebug_after_labels_bb(bb);
        if (gsi_end_p(gsi))
            continue;
        gimple* stmt = gsi_stmt(gsi);

        gimple_stmt_iterator gsi_end = gsi_last_nondebug_bb(bb);
        gimple* stmt_end = gsi_stmt(gsi_end);
        if (stmt_end == NULL)
            continue;

        bool insert_cond_inst = false;

        for (gimple_stmt_iterator gsi_ = gsi_start_bb(bb); !gsi_end_p(gsi_);
             gsi_next(&gsi_)) {
            gimple* stmt_ = gsi_stmt(gsi_);
            struct tree_cb cb;
            memset(&cb, 0, sizeof(cb));
            tree field_tree =
                walk_gimple_op(stmt_, find_st, (struct walk_stmt_info*)&cb);
            if (field_tree != NULL) {
                switch (cb.flag) {
                    case COND_INST: {
                        if (!insert_cond_inst) {
                            gcc_log("building feedback for cond inst\n");
                            insert_cond_inst = true;
                        }
                        break;
                    }
                    case VAL_INST: {
                        output_to_file("VAL_INST", stmt_, fun);
                        break;
                    }
                    case PROP_INST: {
                        output_to_file("PROP_INST", stmt_, fun);
                        break;
                    }
                }
            }

            struct prop_list* p =
                lookup_prop(gimple_filename(stmt_), gimple_lineno(stmt_));
            if (p && p->idx) {
                gcc_log("building feedback for enable point\n");
                output_to_file("ENABLE_POINT", stmt_, fun);
            }
        }

        if (insert_cond_inst) {
            output_to_file("COND_INST", stmt, fun);
        }
    }
    return 0;
}

struct find_inst_pass : gimple_opt_pass {
    find_inst_pass() : gimple_opt_pass(find_inst_data, g) { init_structs(); }

    virtual unsigned int execute(function* fun) { return find_pass(fun); }
};

}  // namespace

static struct plugin_info find_inst_plugin = {
    .version = "20240602",
    .help = "gcc_find_inst",
};

/* This is the function GCC calls when loading a plugin.  Initialize
   and register further callbacks.  */
int plugin_init(struct plugin_name_args* info,
                struct plugin_gcc_version* version) {
    if (!plugin_default_version_check(version, &gcc_version)) {
        FATAL(
            "GCC and plugin have incompatible versions, expected GCC %s, is %s",
            gcc_version.basever, version->basever);
    }

    SAYF(cCYA "[GCC_FIND_INST] Plugin is active" cRST "\n");
    const char* name = info->base_name;
    register_callback(name, PLUGIN_INFO, NULL, &find_inst_plugin);

    find_inst_pass* mypass = new find_inst_pass();
    struct register_pass_info pass_info = {
        .pass = mypass,
        .reference_pass_name = "ssa",
        .ref_pass_instance_number = 1,
        .pos_op = PASS_POS_INSERT_AFTER,
    };

    register_callback(name, PLUGIN_PASS_MANAGER_SETUP, NULL, &pass_info);

    return 0;
}
