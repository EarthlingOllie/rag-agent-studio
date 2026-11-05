# For every resource block in each data module's main.tf: does the AWS provider schema give it a tags
# argument, does main.tf set tags on it, and does the module's every_resource_carries_the_standard_tags run
# assert on it. Usage: python3 -I tagcheck.py <provider schema json> <infra/modules dir>
import json, re, sys
schema_path, modules_dir = sys.argv[1:]
schema = json.load(open(schema_path))['provider_schemas']['registry.terraform.io/hashicorp/aws']['resource_schemas']
bad = total = taggable_n = 0
for module in ['kms', 'database', 'cache', 'storage']:
    main = open(f'{modules_dir}/{module}/main.tf').read()
    test = open(f'{modules_dir}/{module}/tests/contract.tftest.hcl').read()
    start = test.index('run "every_resource_carries_the_standard_tags"')
    tag_run = test[start:test.index('\nrun "', start + 1)]
    print(f'== {module}\n{"resource":58} {"taggable":9} {"sets tags":10} asserted')
    for rtype, rname, body in re.findall(r'^resource "([a-z0-9_]+)" "([a-z0-9_]+)" \{(.*?)^\}', main, re.S | re.M):
        ref = f'{rtype}.{rname}'
        taggable = 'tags' in schema[rtype]['block']['attributes']
        sets = bool(re.search(r'^\s*tags\s*=', body, re.M))
        asserted = ref in tag_run
        ok = (not taggable) or (sets and asserted)
        total += 1; taggable_n += taggable; bad += not ok
        print(f'{ref:58} {str(taggable):9} {str(sets):10} {asserted}{"" if ok else "   <-- MISSING"}')
print(f'\n{total} resources, {taggable_n} taggable, {bad} missing tags or a tag assertion')
sys.exit(1 if bad else 0)
