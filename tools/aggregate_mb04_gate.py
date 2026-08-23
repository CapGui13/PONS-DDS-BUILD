import glob,json,os
ss=[json.load(open(p)) for p in sorted(glob.glob('incoming/S*_SUMMARY.json'))]
assert len(ss)==5
deals=sum(x['deals'] for x in ss); changed=sum(x['changed'] for x in ss); exact=sum(x['exact_mb04'] for x in ss); collateral=sum(x['collateral'] for x in ss)
assert deals==100000
status='FINAL_GATE_PASS' if changed>0 and collateral==0 and exact==changed and all(x['status']=='SHARD_PASS' for x in ss) else 'FINAL_GATE_FAIL'
out={'baseline':'R7_FIXED_MB03_D9_D13_BRANCHK_GREEN','candidate':'R7_FIXED_MB04_DELAYED_SPADES_RKCB_AFTER_OPENER_3S','deals':deals,'same':deals-changed,'changed':changed,'exact_mb04':exact,'collateral':collateral,'status':status,'mb03_critic_sha256':'7f8c10371be03ed35729f7ca0adbd8a374ebd01afed90aa987fc94ae4e02d35a','mb04_critic_sha256':'0838c8bba44bea70a7faf719d180683de45c7d5a8c5753483eed5bbdd68c7e8c','mb04_patch_sha256':'562f2f40e6730c081c7189373ab8c8f5acd2ad29e2d2733db1389c6ad52b41d3','shards':ss}
os.makedirs('final',exist_ok=True)
json.dump(out,open('final/FINAL_GATE_SUMMARY.json','w'),indent=2,sort_keys=True)
print(json.dumps(out,indent=2))
assert status=='FINAL_GATE_PASS'
