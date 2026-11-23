import numpy as np
from scipy import stats

def wilson(k, n, z=1.959963985):
    p = k/n
    d = 1 + z*z/n
    c = (p + z*z/(2*n))/d
    h = z*np.sqrt(p*(1-p)/n + z*z/(4*n*n))/d
    return 100*(c-h), 100*(c+h)

print('='*72); print('1. ACCURACY POINT ESTIMATES AND WILSON CIs'); print('='*72)
rows = [('Fingerling',50,60),('Post-fingerling',47,54),('Juvenile',38,42),('ALL',135,156)]
for nm,k,n in rows:
    lo,hi = wilson(k,n)
    print(f'{nm:16} {k:3}/{n:3} = {100*k/n:6.2f} %   Wilson 95% CI [{lo:.1f}, {hi:.1f}]')

print(); print('='*72); print('2. ROUND-LEVEL AGREEMENT (paired t / Bland-Altman)'); print('='*72)
ref  = np.array([20,20,20,18,18,18,14,14,14], float)
auto = np.array([17,16,17,16,15,16,13,12,13], float)
d = ref-auto
print('differences        :', d.astype(int).tolist())
print(f'mean bias          : {d.mean():.4f}  SD {d.std(ddof=1):.4f}')
t,p = stats.ttest_rel(ref, auto)
print(f'paired t           : t = {t:.4f}, df = {len(d)-1}, p = {p:.6f}')
lo,hi = d.mean()-1.96*d.std(ddof=1), d.mean()+1.96*d.std(ddof=1)
print(f'Bland-Altman LoA   : [{lo:.3f}, {hi:.3f}]')
rel = 100*d/ref
print(f'mean rel undercount: {rel.mean():.3f} %  SD {rel.std(ddof=1):.3f}')
# CV of per-round accuracy within class
acc = 100*auto/ref
for nm, sl in [('Fingerling',slice(0,3)),('Post-fingerling',slice(3,6)),('Juvenile',slice(6,9))]:
    a = acc[sl]
    print(f'  CV {nm:16}: mean {a.mean():.2f} %, SD {a.std(ddof=1):.3f}, CV {100*a.std(ddof=1)/a.mean():.2f} %')

print(); print('='*72); print('3. TREND / HOMOGENEITY'); print('='*72)
k = np.array([50,47,38]); n = np.array([60,54,42]); scores = np.array([1,2,3])
# Cochran-Armitage
N = n.sum(); K = k.sum(); pbar = K/N
num = np.sum(n*(scores-np.sum(n*scores)/N)*(k/n - pbar))
var = pbar*(1-pbar)*np.sum(n*(scores-np.sum(n*scores)/N)**2)
z = num/np.sqrt(var)
print(f'Cochran-Armitage   : z = {z:.4f}, two-sided p = {2*(1-stats.norm.cdf(abs(z))):.4f}')
tab = np.array([k, n-k])
chi2, pchi, dof, _ = stats.chi2_contingency(tab, correction=False)
print(f'Chi-square (2x3)   : chi2 = {chi2:.4f}, df = {dof}, p = {pchi:.4f}')

print(); print('='*72); print('4. mAP@0.5 vs COUNTING ACCURACY (n = 3)'); print('='*72)
m = np.array([0.727,0.777,0.961]); a3 = np.array([83.33,87.04,90.48])
r_,p_ = stats.pearsonr(m, a3)
print(f'Pearson r = {r_:.4f}, p = {p_:.4f}   (n = 3, df = 1)')

print(); print('='*72); print('5. CLUSTERING: IS THE WILSON CI HONEST?'); print('='*72)
print('The 156 passages are not 156 independent Bernoulli trials:')
print('  - the same 20 / 18 / 14 fish are re-used across the 3 rounds of their class')
print('  - fish within a round share water, light, clustering and operator state')
succ = auto; tot = ref
phat = succ.sum()/tot.sum()
# design effect via between-round overdispersion (ratio estimator, cluster bootstrap)
rng = np.random.default_rng(0)
bs = []
for _ in range(200000):
    idx = rng.integers(0, 9, 9)
    bs.append(succ[idx].sum()/tot[idx].sum())
bs = np.array(bs)
lo_b, hi_b = np.percentile(bs, [2.5, 97.5])
print(f'  naive Wilson  95% CI : [{wilson(135,156)[0]:.1f}, {wilson(135,156)[1]:.1f}]  (width {wilson(135,156)[1]-wilson(135,156)[0]:.1f} pp)')
print(f'  cluster bootstrap CI : [{100*lo_b:.1f}, {100*hi_b:.1f}]  (width {100*(hi_b-lo_b):.1f} pp, 9 rounds resampled)')
# design effect
p_r = succ/tot
w = tot/tot.sum()
var_cluster = np.sum(w**2*np.var(bs))  # not used
print(f'  round-level accuracies: {np.round(100*p_r,2).tolist()}')
print(f'  SD of round accuracy  : {100*p_r.std(ddof=1):.2f} pp')
