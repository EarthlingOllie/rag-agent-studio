# Lists every resource in the network module, whether the AWS provider schema lets it carry tags,
# whether main.tf sets tags on it, and whether the tag test asserts on it.
import json, re, sys
schema_path, main_path, test_path = sys.argv[1:]
schema = json.load(open(schema_path))['provider_schemas']['registry.terraform.io/hashicorp/aws']['resource_schemas']
main = open(main_path).read()
test = open(test_path).read()
tag_runs = test[test.index('run "every_fck_nat_mode_resource'):test.index('run "locks_down_the_default_security_group"')]
blocks = re.findall(r'^resource "([a-z0-9_]+)" "([a-z0-9_]+)" \{(.*?)^\}', main, re.S | re.M)
bad = 0
print(f'{"resource":58} {"taggable":9} {"sets tags":10} asserted')
for rtype, rname, body in blocks:
    taggable = 'tags' in schema[rtype]['block']['attributes']
    sets = bool(re.search(r'^\s*tags\s*=', body, re.M))
    ref = f'{rtype}.{rname}'
    asserted = ref in tag_runs or (rtype == 'aws_subnet' and f'{rtype}.{rname}' in tag_runs) or (ref == 'aws_vpc_endpoint.interface' and 'values(aws_vpc_endpoint.interface)' in tag_runs)
    ok = (not taggable) or (sets and asserted)
    bad += not ok
    print(f'{ref:58} {str(taggable):9} {str(sets):10} {asserted}{"" if ok else "   <-- MISSING"}')
print(f'\n{len(blocks)} resources, {sum(1 for b in blocks if "tags" in schema[b[0]]["block"]["attributes"])} taggable, {bad} missing tags or a tag assertion')
sys.exit(1 if bad else 0)
