import glob,json,os
ss=[json.load(open(p)) for p in sorted(glob.glob('incoming/S*_SUMMARY.json'))]
assert len(ss)==5
deals=sum(x['deals'] for x in ss); changed=sum(x['changed'] for x in ss); exact=sum(x['exact_mb06'] for x in ss); collateral=sum(x['collateral'] for x in ss)
assert deals==100000
status='FINAL_GATE_PASS' if changed>0 and collateral==0 and exact==changed and all(x['status']=='SHARD_PASS' for x in ss) else 'FINAL_GATE_FAIL'
out={'baseline':'R7_FIXED_MB05_D9_D13_BRANCHK_DELAYED_SPADES_DELAYED_HEARTS_GREEN','candidate':'R7_FIXED_MB06_O2_SIXCARD_WEAK_JUMP_ROLLBACK','deals':deals,'same':deals-changed,'changed':changed,'exact_mb06':exact,'collateral':collateral,'status':status,'mb05_critic_sha256':'cd3ff1ef67e4848b14f526cf0de0c929f9b3df856e0d847b7a37002cf1898468','mb06_critic_sha256':'6f74d0d55ecf63e8679c21b5f46fc50a48545f9d41cdcc4f26cc51dec4db701c','mb06_patch_sha256':'39832c8bd153a3ec19360fc47e46c79633f685b178f85567477fb35279e6fa48','historical_o2_replay':{'root_cases':3318,'six_card_changes':2261,'mb06_vs_mb05_better':803,'mb06_vs_mb05_worse':630,'mb06_vs_mb05_equivalent':828,'dealer_par_gap_improvement':44320,'root_gap_before':46560,'root_gap_after':2240},'shards':ss}
os.makedirs('final',exist_ok=True)
json.dump(out,open('final/FINAL_GATE_SUMMARY.json','w'),indent=2,sort_keys=True)
print(json.dumps(out,indent=2))
assert status=='FINAL_GATE_PASS'
