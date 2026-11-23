"""Build the corrected manuscript PDF."""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, PageBreak, KeepTogether)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

OUT = os.environ.get('MS_OUT', 'manuscript.pdf')

# --- fonts: use Times New Roman for full Unicode (Greek, superscripts) ---
F = 'Times-Roman'; FB = 'Times-Bold'; FI = 'Times-Italic'; FBI = 'Times-BoldItalic'
WF = r'C:\Windows\Fonts'
try:
    pdfmetrics.registerFont(TTFont('TNR', os.path.join(WF, 'times.ttf')))
    pdfmetrics.registerFont(TTFont('TNR-B', os.path.join(WF, 'timesbd.ttf')))
    pdfmetrics.registerFont(TTFont('TNR-I', os.path.join(WF, 'timesi.ttf')))
    pdfmetrics.registerFont(TTFont('TNR-BI', os.path.join(WF, 'timesbi.ttf')))
    pdfmetrics.registerFontFamily('TNR', normal='TNR', bold='TNR-B',
                                  italic='TNR-I', boldItalic='TNR-BI')
    F, FB, FI, FBI = 'TNR', 'TNR-B', 'TNR-I', 'TNR-BI'
except Exception as e:
    print('font fallback:', e)

ss = getSampleStyleSheet()
def st(name, **kw):
    base = dict(name=name, fontName=F, fontSize=10, leading=13.5,
                alignment=TA_JUSTIFY, spaceAfter=6)
    base.update(kw)
    return ParagraphStyle(**base)

S = {
    'title': st('title', fontName=FB, fontSize=15, leading=19,
                alignment=TA_CENTER, spaceAfter=10),
    'auth': st('auth', fontSize=11, alignment=TA_CENTER, spaceAfter=3),
    'affil': st('affil', fontSize=8.5, leading=11, alignment=TA_CENTER,
                spaceAfter=3, textColor=colors.HexColor('#333333')),
    'h1': st('h1', fontName=FB, fontSize=12, leading=15, spaceBefore=12,
             spaceAfter=5, alignment=0),
    'h2': st('h2', fontName=FBI, fontSize=10.5, leading=13.5, spaceBefore=9,
             spaceAfter=4, alignment=0),
    'body': st('body'),
    'abs': st('abs', fontSize=9, leading=12),
    'cap': st('cap', fontSize=8.5, leading=11, spaceBefore=3, spaceAfter=9,
              textColor=colors.HexColor('#222222')),
    'ref': st('ref', fontSize=8, leading=10, spaceAfter=3,
              firstLineIndent=-12, leftIndent=12),
    'note': st('note', fontSize=9, leading=12, leftIndent=8, rightIndent=8,
               spaceBefore=4, spaceAfter=8,
               borderColor=colors.HexColor('#999999'), borderWidth=0.6,
               borderPadding=5, backColor=colors.HexColor('#F4F4F0')),
    'tcell': st('tcell', fontSize=8, leading=10, alignment=0, spaceAfter=0),
    'thead': st('thead', fontName=FB, fontSize=8, leading=10, alignment=0,
                spaceAfter=0),
}

def P(t, s='body'):
    return Paragraph(t, S[s])

FIGDIR = os.environ.get('FIGDIR', 'docs/manuscript_figs')
FIGMAP = {}
if os.path.isdir(FIGDIR):
    for fn in sorted(os.listdir(FIGDIR)):
        if fn.startswith('fig') and fn.endswith('.png'):
            FIGMAP[int(fn[3:5])] = os.path.join(FIGDIR, fn)

def fig(n, caption, maxw=440, maxh=360):
    """Image flowable + caption, kept on one page."""
    items = []
    path = FIGMAP.get(n)
    if path and os.path.exists(path):
        from reportlab.lib.utils import ImageReader
        iw, ih = ImageReader(path).getSize()
        w = maxw
        h = w * ih / iw
        if h > maxh:
            h = maxh
            w = h * iw / ih
        from reportlab.platypus import Image as RLImage
        im = RLImage(path, width=w, height=h)
        im.hAlign = 'CENTER'
        items.append(im)
        items.append(Spacer(1, 3))
    items.append(P(caption, 'cap'))
    return KeepTogether(items)

def tbl(data, widths, align_right=None, header=True):
    rows = []
    for i, r in enumerate(data):
        sty = 'thead' if (header and i == 0) else 'tcell'
        rows.append([Paragraph(str(c), S[sty]) for c in r])
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0, hAlign='LEFT')
    cmds = [
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('LINEABOVE', (0, 0), (-1, 0), 0.9, colors.black),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
        ('LINEBELOW', (0, -1), (-1, -1), 0.9, colors.black),
    ]
    t.setStyle(TableStyle(cmds))
    return t

def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont(F, 8)
    canvas.setFillColor(colors.HexColor('#555555'))
    canvas.drawCentredString(A4[0] / 2, 12 * mm, str(doc.page))
    canvas.restoreState()

story = []
A = story.append

# ============================ FRONT MATTER ============================
A(P('A Smartphone-Based Computer Vision System for Counting and Size-Sorting '
    'African Catfish (<i>Clarias gariepinus</i>) Fingerlings: Integrating '
    'YOLOv8n Detection with a Feed-Stimulated, Flow-Assisted Transfer Protocol',
    'title'))
A(P('Olaiya Flourish Daniel', 'auth'))
A(P('Department of Agricultural and Bio-Resources Engineering, College of Engineering, '
    'Federal University of Agriculture, Abeokuta, Ogun State, Nigeria', 'affil'))
A(P('Correspondence: flourisholaiya@gmail.com&#160;&#160;·&#160;&#160;ORCID: '
    '<b>[AUTHOR TO VERIFY: insert ORCID iD — required by most Springer journals for the '
    'corresponding author; register free at orcid.org if you do not hold one]</b>', 'affil'))
A(Spacer(1, 8))

A(P('<b>ABSTRACT</b>', 'h1'))
A(P(
    'Accurate enumeration of fingerlings is the hinge on which hatchery stocking density, feed '
    'budgeting, mortality accounting and sales reconciliation all turn, yet most Nigerian '
    'hatcheries still count by hand. Imported optical counters exceed 95&#160;% accuracy but cost '
    'USD&#160;3,000–15,000, which places them beyond the small- and medium-scale producers who '
    'supply the bulk of Nigeria&#8217;s farmed catfish. This study developed and validated a '
    'software-only counting and size-sorting system that operates on video from an ordinary '
    'smartphone, together with the behavioural protocol required to present the fish to the camera '
    'in the first place. A YOLOv8n detector was fine-tuned on 332 annotated images (769 instances) '
    'spanning three size classes defined by head width, and coupled to a lightweight SORT-style '
    'tracker, a mid-frame counting line with downstream direction gating, and majority-vote class '
    'assignment, exposed through a Flask interface. Fingerlings were transferred between a 10&#160;L '
    'source tank and a 13.25&#160;L destination tank through a PVC pipe fitted with an open '
    'observation window. Under flow alone the fish displayed positive rheotaxis and would not enter '
    'the pipe; continuous addition of 2&#160;mm sinking pellet under steady throttled flow produced '
    'reliable downstream movement within minutes, and this feed-stimulated, flow-assisted protocol '
    'became the standard operating procedure. On a validation partition of 66 images (157 instances) '
    'the model attained mAP@0.5&#160;=&#160;0.822, mAP@0.5:0.95&#160;=&#160;0.479, precision 0.812, '
    'recall 0.782 and F1&#160;=&#160;0.797; on the held-out test partition (34 images, 62 instances) '
    'mAP@0.5&#160;=&#160;0.832 and F1&#160;=&#160;0.813. Because all imagery derives from a single '
    '43-minute acquisition session, these are within-session estimates and are not a measure of '
    'cross-session generalisation. Against a hand-counted reference over nine rounds and 156 fish '
    'passages, the system recovered 135 fish (86.5&#160;%; 95&#160;% CI 80.3–91.0; cluster bootstrap '
    'over rounds 84.1–89.2). Accuracy rose with fish size (83.3, 87.0 and 90.5&#160;% for '
    'fingerlings, post-fingerlings and juveniles) although the trend was not statistically '
    'significant (Cochran–Armitage z&#160;=&#160;1.05, p&#160;=&#160;0.294). Within the scored '
    'passages every error was an undercount, with a mean bias of 2.33 fish per round '
    '(paired t&#160;=&#160;7.00, p&#160;&lt;&#160;0.001), indicating a systematic and therefore '
    'correctable detection deficit rather than random noise; false positives observed outside the '
    'validated envelope are reported separately in Section&#160;3.6. The system is positioned as the '
    'lowest-capital-cost automated option so far reported for this task, at an accuracy 8–10 '
    'percentage points below commercial optical counters.', 'abs'))
A(Spacer(1, 4))
A(P('<b>Keywords:</b> <i>Clarias gariepinus</i>; fingerling counting; YOLOv8; multi-object '
    'tracking; positive rheotaxis; smallholder aquaculture; smartphone imaging; low-resource '
    'automation.', 'abs'))

# ============================ 1. INTRO ============================
A(P('1.&#160;&#160;Introduction', 'h1'))
A(P('Aquaculture supplies a growing share of the animal protein consumed in sub-Saharan Africa, and '
    'in Nigeria the African catfish, <i>Clarias gariepinus</i> (Burchell, 1822), accounts for the '
    'large majority of farmed fish by volume (FAO, 2022; Adewumi, 2021). The species is favoured for '
    'its hardiness, rapid growth, tolerance of low dissolved oxygen through an accessory '
    'air-breathing organ, and its established value chain from hatchery to grow-out (Bruton, 1979; '
    'Viveen et al., 1985). Production passes through fry, fingerling, post-fingerling, juvenile and '
    'adult phases, each with distinct stocking, feeding and grading requirements.'))
A(P('The fingerling and post-fingerling phases carry the greatest commercial weight. Fingerlings are '
    'simultaneously the hatchery&#8217;s principal saleable product and the grow-out farm&#8217;s '
    'starting stock, so the count recorded at the moment of sale, stocking or transfer propagates '
    'into every downstream decision: stocking density, feed budgeting, mortality estimation, book '
    'reconciliation and the settlement of disputes between hatchery and buyer (Li et al., 2021; '
    'Zhang et al., 2021). An error committed at this point is not self-correcting; it is carried '
    'silently through the cycle and surfaces later as unexplained loss.'))
A(P('Despite these stakes, enumeration in most Nigerian hatcheries remains manual. Fish are scooped '
    'into a shallow bowl and either tallied individually or estimated against a calibrated cup. '
    'Individual tallying is accurate for small batches but scales poorly, and its accuracy degrades '
    'measurably with batch size, operator fatigue and declining light; volumetric and weight-based '
    'shortcuts trade accuracy for speed (Saberioon and Císař, 2018; Li et al., 2021). Repeated '
    'handling additionally imposes a physiological stress load that contributes to post-handling '
    'mortality and depressed subsequent growth (Barton, 2002; Ashley, 2007).'))
A(P('Commercially available optical counters resolve both the accuracy and the labour problem, '
    'routinely exceeding 95&#160;% accuracy, but at manufacturer prices of USD&#160;3,000–15,000 '
    'before import duty, freight, customs and local margin. The installed cost in Nigeria frequently '
    'exceeds the annual operating budget of a typical small farm, and dependence on imported spares '
    'and foreign service technicians deepens the reluctance to invest. The result is a persistent '
    'capability gap that neither commercial nor local prototypes have closed at scale.'))
A(P('Two developments make closing that gap plausible. The first is the maturation of single-stage '
    'object detectors, particularly the You Only Look Once (YOLO) family, which recast detection as '
    'a single regression pass and thereby achieve high throughput without the two-stage overhead of '
    'R-CNN derivatives (Redmon et al., 2016; Ren et al., 2015; Jocher et al., 2023). The second is '
    'the ubiquity of the smartphone: nearly every Nigerian fish farmer already owns a device with a '
    'camera adequate to the task. Building the system around a phone rather than a dedicated '
    'industrial camera is the single largest cost-eliminating decision available, and recent work '
    'has confirmed that smartphone-acquired imagery can support accurate deep-learning fish counts '
    '(Costa et al., 2022).'))
A(P('A third factor is less frequently discussed and proved, in this work, to be decisive. Published '
    'counting prototypes concentrate almost exclusively on the detector, the dataset and the '
    'resulting accuracy figures, while treating the delivery of fish to the camera as a solved or '
    'trivial matter (Zhang et al., 2020; Li et al., 2021; Gonçalves et al., 2022). It is not. '
    '<i>Clarias gariepinus</i> exhibits positive rheotaxis, orienting into and holding station '
    'against an oncoming current (Arnold, 1974; Montgomery et al., 1997), which means that '
    'connecting two tanks with flowing water does not, by itself, cause fingerlings to travel from '
    'one to the other. A detector of arbitrary quality cannot count fish that decline to move past '
    'it.'))
A(P('This study therefore treats fish delivery as a first-class engineering variable rather than a '
    'boundary condition. The specific objectives were: (i) to assemble and annotate an image dataset '
    'of <i>C.&#160;gariepinus</i> spanning three size classes; (ii) to develop a '
    'smartphone-deployable counting and size-sorting pipeline built on YOLOv8n detection, '
    'centroid-association tracking and counting-line logic; (iii) to quantify detection performance '
    'using mAP, precision, recall and F1; and (iv) to quantify counting accuracy and its agreement '
    'with a hand-counted reference, and to situate the result against manual, semi-automatic and '
    'commercial benchmarks. No counting machine was fabricated: the deliverable is the software, the '
    'validated recording geometry, and the behavioural protocol that makes the recording possible.'))

# ============================ 2. METHODS ============================
A(P('2.&#160;&#160;Materials and Methods', 'h1'))

A(P('2.1&#160;&#160;Study site, experimental animals and size classes', 'h2'))
A(P('The work was carried out under controlled conditions on the campus of the Federal University of '
    'Agriculture, Abeokuta (FUNAAB), Ogun State, Nigeria, using clean fresh water and natural '
    'ambient daylight. Live <i>C.&#160;gariepinus</i> were sourced from commercial hatcheries in '
    'Abeokuta. Three size classes were defined by head width, which is the dimension a hatchery '
    'operator uses in practice when grading through a mesh: fingerling (&lt;&#160;0.65&#160;cm), '
    'post-fingerling (0.65–1.00&#160;cm) and juvenile (1.00–1.50&#160;cm), corresponding '
    'approximately to total lengths of 3–5&#160;cm, 5–9&#160;cm and &#8805;&#160;10&#160;cm '
    'respectively. Fry below 3&#160;cm total length were excluded, since the recording geometry was '
    'not designed for them and the model was not trained on that size.'))

A(P('2.2&#160;&#160;Transfer rig and observation section', 'h2'))
A(P('A two-tank arrangement was assembled from off-the-shelf containers to reproduce, at benchtop '
    'scale, the pond-to-pond transfer during which a farmer would realistically record a count '
    '(Fig.&#160;1, Fig.&#160;2). A rectangular source tank (Tank&#160;1; internal dimensions '
    '0.20&#160;×&#160;0.20&#160;×&#160;0.25&#160;m) discharges by gravity through a PVC pipe into a '
    'cylindrical destination tank (Tank&#160;2; internal diameter 0.250&#160;m, water column '
    '0.270&#160;m). A rectangular window was cut in the upper wall of the pipe to form an open '
    'observation section, above which the smartphone is positioned; the water surface within the '
    'section is open to air and is not covered by glazing. A mesh screen over the destination '
    'outflow retains arriving fish while allowing water to escape.'))
A(P('The rig was sized from first principles. Tank volumes follow from'))
A(P('<i>V</i><sub>1</sub> = <i>L</i>&#160;×&#160;<i>W</i>&#160;×&#160;<i>H</i> = '
    '0.20&#160;×&#160;0.20&#160;×&#160;0.25 = 0.0100&#160;m<super>3</super> = 10.0&#160;L'
    '&#160;&#160;&#160;&#160;(1)'))
A(P('<i>V</i><sub>2</sub> = &#960;<i>r</i><super>2</super><i>H</i> = '
    '&#960;&#160;×&#160;(0.125)<super>2</super>&#160;×&#160;0.270 = '
    '0.01325&#160;m<super>3</super> &#8776; 13.25&#160;L&#160;&#160;&#160;&#160;(2)'))
A(P('so that the destination tank comfortably absorbs the volume transferred within a round without '
    'overflowing. The hydrostatic pressure available at the source-tank base with a full '
    '0.25&#160;m column is'))
A(P('<i>P</i> = &#961;<i>gH</i> = 1000&#160;×&#160;9.81&#160;×&#160;0.25 = 2452.5&#160;Pa '
    '&#8776; 2.45&#160;kPa&#160;&#160;&#160;&#160;(3)'))
A(P('The observation section is a 100&#160;mm nominal-bore pipe with the upper wall removed, '
    'operated at a water depth of 0.05&#160;m. The wetted cross-section is therefore a circular '
    'segment rather than a rectangle, and is obtained from'))
A(P('<i>A</i> = <i>r</i><super>2</super>(&#952; &#8722; sin&#160;&#952;)/2,&#160;&#160;'
    '&#952; = 2&#160;arccos((<i>r</i> &#8722; <i>h</i>)/<i>r</i>)&#160;&#160;&#160;&#160;(4)'))
A(P('which for <i>r</i>&#160;=&#160;0.050&#160;m and <i>h</i>&#160;=&#160;0.050&#160;m gives '
    '&#952;&#160;=&#160;&#960; and <i>A</i>&#160;=&#160;&#960;<i>r</i><super>2</super>/2 '
    '=&#160;0.00393&#160;m<super>2</super>. An earlier formulation of this work applied the '
    'rectangular form <i>A</i>&#160;=&#160;<i>bh</i>&#160;=&#160;0.005&#160;m<super>2</super>, which '
    'overstates the true wetted area of a part-full circular pipe by approximately 27&#160;%. '
    '<b>[AUTHOR TO VERIFY: Detail&#160;A of Fig.&#160;1 draws the observation section as a '
    'rectangular channel of 100&#160;×&#160;50&#160;mm, which is consistent with the original '
    '<i>A</i>&#160;=&#160;<i>bh</i> formulation but not with the as-built rig visible in the '
    'field recordings, which is a cylindrical PVC pipe with the upper wall cut away. Either the '
    'drawing or the equation must change. If the section really is a rectangular flume, revert '
    'Eq.&#160;(4) to <i>bh</i> and delete this paragraph; if it is a cut pipe, redraw Detail&#160;A '
    'to match.]</b> The deliberately wide and shallow geometry constrains the fish to pass the camera in approximately '
    'a single layer, which sharpens each detection and reduces mutual occlusion — the design '
    'decision that later proved most consequential for the larger size classes.'))
A(fig(1, '<b>Figure 1.</b> Orthographic projection of the two-tank transfer rig, showing the plan and '
    'elevation views together with the open-channel observation cross-section (Detail&#160;A) and '
    'the mesh-screened outflow tap that retains arriving fish (Detail&#160;B). All dimensions in '
    'millimetres.'))
A(fig(2, '<b>Figure 2.</b> The assembled rig in operation. (a) Source tank, connecting pipe and '
    'destination tank with mesh-screened outflow. (b) Plan view of the open observation window with '
    'fingerlings in transit; the shallow, wide cross-section holds the fish in a near-single layer '
    'beneath the smartphone.'))

A(P('2.3&#160;&#160;Image dataset and annotation', 'h2'))
A(P('A dataset of 332 images containing 769 annotated instances was acquired with a 12&#160;MP '
    'smartphone camera under natural daylight, held square to the water surface so as to reproduce '
    'the recording geometry of the deployed system (Fig.&#160;3). Each fish was given a tight '
    'bounding box and one of three class labels on the Roboflow platform (Dwyer et al., 2023); '
    'representative annotated samples are shown in Fig.&#160;4. The dataset was partitioned 70/20/10 '
    'into training (232 images), validation (66) and test (34) subsets by random split.'))
A(P('The class distribution is not balanced (Table&#160;1). By annotated instance the dataset is '
    '51.4&#160;% fingerling, 36.2&#160;% post-fingerling and 12.5&#160;% juvenile; by dominant class '
    'per image it is 39.5&#160;/&#160;39.8&#160;/&#160;20.8&#160;%. The juvenile class is '
    'under-represented by roughly 2:1. This imbalance is reported because it strengthens rather than '
    'weakens the interpretation offered in Sections&#160;3.2 and 4.2: the juvenile class carries the '
    '<i>fewest</i> training instances and achieves the <i>best</i> detection performance, so the '
    'observed size effect cannot be an artefact of training-data volume.'))
A(P('Augmentation was applied on-the-fly during training using the Ultralytics defaults, as recorded '
    'in the training checkpoint: HSV jitter (hue 0.015, saturation 0.7, value 0.4), translation 0.1, '
    'scale 0.5, horizontal flip 0.5, mosaic 1.0, random erasing 0.4 and mosaic closure over the '
    'final 10 epochs. No offline augmented copies were exported. Notably, rotation and vertical flip '
    'were <i>not</i> applied (degrees&#160;=&#160;0.0, flipud&#160;=&#160;0.0), nor was Gaussian '
    'blur. Because fish present at arbitrary orientation within the channel, the absence of rotation '
    'and vertical-flip augmentation is identified in Section&#160;5 as a concrete improvement lead.'))

A(Spacer(1, 2))
A(P('<b>Table 1.</b> Composition of the curated dataset and the head-width criteria defining each '
    'developmental class. Counts are annotated instances, taken directly from the exported COCO '
    'annotation files; most images contain several fish, so an images-per-class column would be '
    'ambiguous for mixed groups.', 'cap'))
A(tbl([
    ['Class', 'Head width (cm)', 'Approx. total length (cm)', 'Train', 'Valid', 'Test',
     'Total instances', 'Share (%)'],
    ['Fingerling', '&lt; 0.65', '3–5', '284', '90', '21', '395', '51.4'],
    ['Post-fingerling', '0.65–1.00', '5–9', '202', '48', '28', '278', '36.2'],
    ['Juvenile', '1.00–1.50', '&#8805; 10', '64', '19', '13', '96', '12.5'],
    ['<b>Total instances</b>', '—', '—', '<b>550</b>', '<b>157</b>', '<b>62</b>',
     '<b>769</b>', '<b>100.0</b>'],
    ['<b>Total images</b>', '—', '—', '<b>232</b>', '<b>66</b>', '<b>34</b>',
     '<b>332</b>', '—'],
], [62, 52, 62, 32, 30, 28, 48, 34]))
A(Spacer(1, 6))

A(P('<b>A note on split independence.</b> All 332 images were acquired within a single 43-minute '
    'session on one day. The 70/20/10 partition is random across frames from that session, so '
    'frames separated by very short intervals — and therefore depicting the same individuals, water, '
    'illumination and camera pose — are distributed across the training, validation and test '
    'subsets. Measured from the acquisition timestamps, 50&#160;% of validation images and '
    '59&#160;% of test images were captured within 2&#160;s of a training image, and 79&#160;% and '
    '94&#160;% respectively within 5&#160;s. The detection metrics in Section&#160;3.2 must '
    'therefore be read as <i>within-session</i> performance. They are not an estimate of '
    'generalisation to new sessions, new individuals, new illumination or new sites, and no such '
    'claim is made here. Section&#160;5 sets out the session-wise acquisition and splitting protocol '
    'required to obtain that estimate.', 'note'))

A(fig(3, '<b>Figure 3.</b> Representative specimens of the three developmental classes as acquired for '
    'the dataset: (a,&#160;d) fingerling, (b,&#160;e) post-fingerling, (c,&#160;f) juvenile; single '
    'specimens above, grouped specimens in shallow trays below. Images were captured square to the '
    'water surface under natural daylight to match deployment geometry.'))
A(fig(4, '<b>Figure 4.</b> Bounding-box annotation on Roboflow: (a) a densely populated fingerling frame, '
    '(b) an overlapping post-fingerling frame, and (c) an isolated juvenile. Dense, mutually '
    'overlapping annotations of the kind shown in (a) and (b) are the training-set counterpart of '
    'the cluster-merge errors observed at inference.'))

A(P('2.4&#160;&#160;Detection model and training', 'h2'))
A(P('YOLOv8n was selected from the Ultralytics family (Jocher et al., 2023). The architecture '
    'comprises a CSPDarknet backbone with C2f modules, a PAN/FPN neck fusing features across scales, '
    'and a decoupled anchor-free head trained with distributional focal loss. Configured for the '
    'three classes used here, the trained model carries 3,011,433 parameters and 8.20&#160;GFLOPs at '
    '640&#160;×&#160;640 input (3,006,233 parameters and 8.1&#160;GFLOPs after layer fusion), which '
    'is light enough for mobile or low-power edge deployment and appropriate to the modest size of '
    'the available dataset.'))
A(P('Training started from COCO-pretrained weights and ran for 100 epochs under Ultralytics 8.4.21 '
    'on a cloud-hosted GPU runtime (Google&#160;Colab). '
    '<b>[AUTHOR TO VERIFY: name the specific accelerator allocated — e.g. Tesla T4 — which is '
    'recorded in the Colab session but not in the checkpoint.]</b> All hyperparameters other than '
    'data path, epochs, batch size, image size, device and worker count were left at the Ultralytics '
    'defaults. In particular the optimiser was left at <font face="%s">optimizer=&#8217;auto&#8217;</font>, '
    'under which Ultralytics selects the optimiser, initial learning rate and momentum automatically '
    'from dataset size and overrides any supplied values; the learning-rate schedule was therefore '
    'linear (<font face="%s">cos_lr=False</font>), not cosine; and early-stopping patience was left '
    'at the default of 100 epochs, so early stopping could not trigger and all 100 epochs ran. '
    'Reporting the defaults explicitly, rather than the values nominally supplied, is necessary for '
    'reproducibility because the supplied values were not the operative ones. Configuration '
    'parameters for training, tracking and counting are consolidated in Table&#160;2.'
    % (F, F)))

A(Spacer(1, 2))
A(P('<b>Table 2.</b> Consolidated configuration of the detection, tracking and counting stages, as '
    'recorded in the training checkpoint and the released configuration file '
    '(<font face="%s">config/config.yaml</font>, commit tagged in the Data and Code Availability '
    'statement).' % F, 'cap'))
A(tbl([
    ['Stage', 'Parameter', 'Value', 'Rationale / source'],
    ['Training', 'Epochs / early stopping', '100 / patience 100 (never triggered)', 'Ultralytics default'],
    ['', 'Optimiser', "optimizer='auto' (Ultralytics selects)", 'Checkpoint train_args'],
    ['', 'Initial LR / schedule', 'Auto-selected / linear decay', 'cos_lr = False'],
    ['', 'Batch size', '16', 'Ultralytics default'],
    ['', 'Input resolution', '640 × 640 px', 'Default YOLOv8 resolution'],
    ['', 'Weight decay', '5 × 10<super>&#8722;4</super>', 'Ultralytics default'],
    ['Inference', 'Confidence threshold', '0.50', 'Count-unbiased operating point (Sec. 3.2)'],
    ['', 'NMS IoU threshold', '0.50', 'Conventional setting'],
    ['', 'Preprocessing', 'CLAHE (clip 2.0, 8 × 8 tiles, LAB)', 'Applied in deployment; see Sec. 3.2'],
    ['Tracking', 'Max age', '30 frames', 'Track persistence through brief loss'],
    ['', 'Min hits', '3 frames', 'Suppresses spurious tracks'],
    ['', 'Association', 'Hungarian on centroid distance', 'See Section 2.5'],
    ['', 'Gating radius', '160 px', 'Rejects implausible associations'],
    ['Counting', 'Line position', 'y = 0.50 (normalised)', 'Mid-frame, maximal approach distance'],
    ['', 'Direction gate', 'Downstream only', 'Rejects reversals and static artefacts'],
    ['', 'Class assignment', 'Majority vote over track', 'Resists isolated misclassified frames'],
], [48, 86, 150, 118]))
A(Spacer(1, 6))

A(P('2.5&#160;&#160;Tracking, counting logic and interface', 'h2'))
A(P('Per-frame detections are associated frame-to-frame by a lightweight SORT-style tracker, '
    'following the design of Bewley et al. (2016): optimal assignment is computed with the Hungarian '
    'algorithm, motion is predicted by constant-velocity extrapolation from the two most recent '
    'centroid positions, and a fixed gating radius of 160&#160;px rejects implausible matches. The '
    'implementation departs from SORT proper in two respects that are stated here because they '
    'affect reproducibility: it uses <i>Euclidean centroid distance</i> rather than '
    'intersection-over-union as the association cost, and it uses constant-velocity extrapolation '
    'rather than a Kalman filter. The simplification is defensible for this geometry — the shallow, '
    'wide observation section keeps fish separated and slow-moving, so the conditions under which a '
    'Kalman filter and IoU association earn their additional cost (dense occlusion, erratic motion) '
    'do not arise — and it is corroborated by the error taxonomy in Section&#160;3.5, in which track '
    'loss was the rarest of the three failure modes in every class. DeepSORT&#8217;s appearance '
    'descriptor (Wojke et al., 2017) was judged unnecessary for the same reason. The complete '
    'pipeline, from acquisition through offline model development to per-frame inference and output, '
    'is set out in Fig.&#160;5.'))
A(P('Counting is performed by a virtual line drawn horizontally across the mid-frame at '
    'y&#160;=&#160;0.50 in normalised coordinates. For every confirmed track the centroid position '
    'in the previous and current frames is compared, and the count is incremented only when the '
    'centroid crosses the line in the downstream direction; upstream crossings are discarded, and a '
    'one-shot flag prevents a track that hesitates and re-crosses from being counted twice. The '
    'class label attached to each counted fish — which constitutes the size sorting — is the modal '
    'label over all frames in which the track retained its identity, a majority vote that absorbs '
    'isolated misclassified frames. The decision logic is given in full in Fig.&#160;6. '
    'Section&#160;3.6 reports a measured comparison of this counting rule against the simpler '
    'unique-track rule, and quantifies how often the majority vote alters the recorded size class.'))
A(P('A Flask server exposes a monitoring interface on TCP port 5000 (Fig.&#160;7). It streams the '
    'annotated video with boxes, track identifiers and the counting line overlaid, displays running '
    'per-class and total counts, and provides start and reset controls. Two logs are written: a '
    'per-frame snapshot of running totals (timestamp, frame, total, per-class counts, processing '
    'frame rate), and a per-fish event record (timestamp, track identifier, assigned class, frame '
    'and bounding box) written at the moment of counting, which permits post-hoc reconstruction of '
    'any round. '
    '<b>[AUTHOR TO VERIFY: the per-fish event log is specified here but is not yet implemented in '
    'the released code — either implement it before submission or delete this sentence and the '
    'auditability claim in Section&#160;4.3.]</b>'))
A(fig(5, '<b>Figure 5.</b> End-to-end architecture of the counting system. Stage&#160;2 is executed once, '
    'offline; stages&#160;1, 3 and 4 run for every deployment. The dual-tank rig and the feed '
    'stimulus are shown as the first block because, as Section&#160;3.1 establishes, they are '
    'functional components of the measurement chain rather than mere experimental scaffolding.'))
A(fig(6, '<b>Figure 6.</b> Per-frame decision logic governing count incrementation. Three sequential '
    'gates — track confirmation, line crossing and direction — must all be satisfied before the '
    'count is incremented; any failure returns control to the next frame without incrementing.'))
A(fig(7, '<b>Figure 7.</b> Flask monitoring interface during a fingerling round, showing running '
    'per-class counts, total, in-frame instantaneous count and class distribution.'))

A(P('2.6&#160;&#160;Movement-stimulus protocol', 'h2'))
A(P('The protocol reported below emerged from a failure during pilot testing and is described here '
    'as a method because it is the condition on which every subsequent measurement depends. With '
    'flowing water alone, fingerlings would not enter the connecting pipe; consistent with positive '
    'rheotaxis they turned to face the inflow and held position, and increasing the flow rate did '
    'not alter the behaviour. Continuous addition of feed changed it immediately. Catfish are '
    'opportunistic feeders with acute olfactory and gustatory sensitivity (Hara, 1994; Kasumyan, '
    '2019), and pellet dissolving in moving water establishes a scent gradient the fish will follow '
    '(Bardach et al., 1967).'))
A(P('Three settings were fixed after pilot runs and held constant throughout: feed type (2&#160;mm '
    'sinking pellet, approximately 5&#160;g per round, identical for all classes), a steady '
    'throttled flow, and a maximum round duration of ten minutes. Discharge was not free: at the '
    'available head of 0.25&#160;m, unrestricted gravity discharge would give a theoretical '
    'efflux velocity of &#8730;(2<i>gH</i>)&#160;=&#160;2.21&#160;m&#160;s<super>&#8722;1</super> '
    'and a flow of order 10<super>1</super>–10<super>2</super>&#160;L&#160;min<super>&#8722;1</super> '
    'depending on bore, which would have swept the fish through the observation section far too '
    'rapidly to image. The discharge was therefore throttled at the outlet to deliver a controlled '
    'flow. '
    '<b>[AUTHOR TO VERIFY — BLOCKING: the flow rate reported in the earlier draft '
    '(0.5&#160;L&#160;min<super>&#8722;1</super>) is not self-consistent with the rest of the '
    'protocol. Over the corrected wetted area of 0.00393&#160;m<super>2</super> it implies a mean '
    'channel velocity of 2.1&#160;mm&#160;s<super>&#8722;1</super> and a transfer time of '
    'approximately 20&#160;minutes for a 10&#160;L volume, which contradicts both the reported '
    'five-to-eight-minute clearing time and the ten-minute round ceiling, and is far below any '
    'velocity capable of eliciting the station-holding rheotaxis that is this study&#8217;s '
    'headline behavioural finding. A flow of order 5&#160;L&#160;min<super>&#8722;1</super> '
    '(17&#160;mm&#160;s<super>&#8722;1</super>, ~2&#160;min transfer) is consistent with the '
    'narrative. Please supply the measured value, the method of measurement (timed volume, '
    'rotameter or other) and the throttling device used, and state whether the velocity relevant to '
    'the rheotaxis observation is the channel mean or the local velocity at the constricted pipe '
    'inlet.]</b>'))

A(P('2.7&#160;&#160;Validation design', 'h2'))
A(P('Two independent validations were performed. Detection performance was scored on the validation '
    'partition (66 images, 157 annotated instances) after 100 training epochs, and separately on the '
    'held-out test partition (34 images, 62 instances), which played no part in model selection. '
    'Counting performance was assessed against a hand-counted reference under a repeated-measures '
    'design: three size classes (fingerling n&#160;=&#160;20, post-fingerling n&#160;=&#160;18, '
    'juvenile n&#160;=&#160;14), each subjected to three independent rounds, giving nine rounds and '
    '156 individual fish passages in total. Each round followed a fixed sequence: the reference '
    'count was established by moving all fish into the source tank and confirming the number by two '
    'independent hand counts; flow was opened and recording started; feed was introduced '
    'continuously; the round ran for up to ten minutes without operator intervention; all fish were '
    'then recovered from both tanks and recounted, and the round was admitted as valid only if every '
    'fish was accounted for. Fish rested for approximately fifteen minutes between rounds.'))

A(P('2.8&#160;&#160;Metrics and statistical analysis', 'h2'))
A(P('Detection was scored with precision, recall, F1 and mean average precision at IoU 0.5 and '
    'averaged over 0.5:0.95. Ultralytics reports precision and recall at the maximum-F1 point of the '
    'precision–recall curve, so F1 computed as 2PR/(P&#160;+&#160;R) from the reported values is '
    'self-consistent; a reader recomputing F1 at a fixed confidence of 0.50 will obtain a slightly '
    'different figure. Counting accuracy per round was computed as the ratio of the automated count '
    'to the reference count, expressed as a percentage; because every observed error within the '
    'scored passages was an undercount, this ratio is numerically equivalent to counting recall, and '
    'it is interpreted as such throughout. Aggregate accuracy is the ratio of summed automated '
    'counts to summed reference counts.'))
A(P('Beyond the point estimates, four additional analyses were performed. Binomial confidence '
    'intervals on counting accuracy were computed by the Wilson score method (Wilson, 1927), which '
    'is preferred to the normal approximation at these sample sizes and proportions. The hypothesis '
    'of a monotonic increase in accuracy with size class was tested with the Cochran–Armitage test '
    'for trend, and homogeneity across classes with Pearson&#8217;s chi-square. Agreement between '
    'the automated and reference counts at the round level was characterised by paired-samples '
    't-test and by the Bland–Altman bias and limits of agreement (Bland and Altman, 1986), which is '
    'the appropriate framing for a method-comparison study and is reported here in preference to '
    'accuracy alone.'))
A(P('Fourth, because the Wilson interval treats the 156 passages as independent Bernoulli trials '
    'when in fact the same 20, 18 and 14 individuals were re-used across the three rounds of their '
    'class — and fish within a round share water, illumination, clustering and operator state — a '
    'cluster bootstrap resampling the nine rounds (200,000 draws) was computed as a sensitivity '
    'check. The effective independent unit is the round, not the passage.'))

# ============================ 3. RESULTS ============================
A(P('3.&#160;&#160;Results', 'h1'))

A(P('3.1&#160;&#160;Movement behaviour: flow alone versus flow with continuous feeding', 'h2'))
A(P('The most consequential observation of the study preceded any counting measurement. Under '
    'continuous flow without feed, across repeated trials, only a handful of fingerlings entered the '
    'connecting pipe; the remainder oriented into the inflow and held station against it, and '
    'raising the flow rate did not dislodge them. This is the textbook positive rheotactic response '
    'of <i>C.&#160;gariepinus</i> (Arnold, 1974; Montgomery et al., 1997), and it constitutes a hard '
    'limit on any counting design that assumes water movement alone will deliver fish to a sensor.'))
A(P('Continuous feeding reversed the behaviour within seconds to two minutes. Fish moved down the '
    'pipe and into the destination tank, drawn by the scent gradient and carried by the flow. '
    'Movement was pulsatile rather than continuous — small groups crossing at intervals — and a '
    'population typically cleared within five to eight minutes, within the ten-minute round ceiling. '
    'This pulsatile pattern has a direct engineering consequence: it concentrates fish into '
    'transient clusters at the observation window, which is precisely the condition under which the '
    'cluster-merge error mode reported in Section&#160;3.5 arises.'))

A(P('3.2&#160;&#160;Detection performance', 'h2'))
A(P('Table&#160;3 and Fig.&#160;8 report detection performance. On the validation partition the '
    'model achieved precision 0.812, recall 0.782, F1 0.797 and mAP@0.5&#160;=&#160;0.822. '
    'Performance was strongly class-dependent. Juveniles were detected reliably '
    '(F1&#160;=&#160;0.936, mAP@0.5&#160;=&#160;0.961), whereas fingerlings and post-fingerlings '
    'scored substantially lower (F1&#160;=&#160;0.733 and 0.719). The mAP@0.5:0.95 of 0.479 is '
    'considerably weaker than the mAP@0.5 figure, indicating that while the model localises fish '
    'well enough to be judged correct at a permissive IoU threshold, box regression is loose at '
    'stricter thresholds — an expected consequence of small object size, motion blur and a modest '
    'training set. Counting depends on detecting a fish rather than on pixel-accurate box geometry, '
    'so this trade-off is favourable for the primary task; it bears more directly on size '
    'classification, which is the weaker of the two claims made here.'))
A(P('Because the checkpoint was selected by fitness on the validation partition, that result is a '
    'model-selection score. Performance on the held-out test partition is therefore reported '
    'alongside it: precision 0.871, recall 0.761, F1 0.813 and mAP@0.5&#160;=&#160;0.832. The test '
    'result is marginally the stronger of the two, indicating that the checkpoint is not overfitted '
    'to the selection partition. As set out in Section&#160;2.3, however, both partitions originate '
    'in the same acquisition session as the training data, so the agreement between them '
    'demonstrates consistency within that session and not generalisation beyond it.'))
A(P('Instance counts are reported per class in Table&#160;3 so that the reader may weight the rows: '
    'the juvenile row rests on 19 validation instances in 13 images and carries a correspondingly '
    'wide interval.'))

A(Spacer(1, 2))
A(P('<b>Table 3.</b> YOLOv8n detection performance on the validation partition (66 images, 157 '
    'instances) and the held-out test partition (34 images, 62 instances), without CLAHE '
    'preprocessing. F1 is derived from precision and recall as 2PR/(P&#160;+&#160;R).', 'cap'))
A(tbl([
    ['Partition', 'Class', 'Instances', 'Precision', 'Recall', 'F1', 'mAP@0.5', 'mAP@0.5:0.95'],
    ['Validation', 'Fingerling', '90', '0.756', '0.711', '0.733', '0.727', '0.378'],
    ['', 'Post-fingerling', '48', '0.754', '0.688', '0.719', '0.777', '0.433'],
    ['', 'Juvenile', '19', '0.926', '0.947', '0.936', '0.961', '0.627'],
    ['', '<b>Overall</b>', '<b>157</b>', '<b>0.812</b>', '<b>0.782</b>', '<b>0.797</b>',
     '<b>0.822</b>', '<b>0.479</b>'],
    ['Test (held out)', 'Fingerling', '21', '0.886', '0.741', '0.807', '0.768', '—'],
    ['', 'Post-fingerling', '28', '0.867', '0.697', '0.773', '0.798', '—'],
    ['', 'Juvenile', '13', '0.861', '0.846', '0.853', '0.929', '—'],
    ['', '<b>Overall</b>', '<b>62</b>', '<b>0.871</b>', '<b>0.761</b>', '<b>0.813</b>',
     '<b>0.832</b>', '<b>0.451</b>'],
], [58, 66, 40, 46, 38, 38, 44, 54]))
A(Spacer(1, 6))

A(P('<b>Preprocessing.</b> The deployed inference path applies contrast-limited adaptive histogram '
    'equalisation (CLAHE; clip limit 2.0, 8&#160;×&#160;8 tiles, in LAB colour space) to every frame '
    'before inference, whereas the model was trained and Table&#160;3 was computed without it. The '
    'effect was measured on the same weights and is reported in Table&#160;4 rather than suppressed, '
    'because it is favourable on the axis that matters: CLAHE raises recall by 5.3 percentage points '
    'on validation and 7.1 on test, at some cost to precision and to tight-IoU localisation. Recall '
    'is precisely the axis on which this system loses fish. The counting rounds reported in '
    'Section&#160;3.3 were run through the CLAHE path.'))
A(Spacer(1, 2))
A(P('<b>Table 4.</b> Effect of CLAHE preprocessing on detection performance (same weights, CPU, '
    '640&#160;×&#160;640 input).', 'cap'))
A(tbl([
    ['Partition', 'Preprocessing', 'Precision', 'Recall', 'F1', 'mAP@0.5', 'mAP@0.5:0.95'],
    ['Validation', 'Raw (as in Table 3)', '0.811', '0.782', '0.796', '0.821', '0.479'],
    ['Validation', 'CLAHE (as deployed)', '0.773', '<b>0.835</b>', '0.803', '<b>0.837</b>', '0.459'],
    ['Test', 'Raw', '0.871', '0.761', '0.813', '0.832', '0.451'],
    ['Test', 'CLAHE (as deployed)', '0.877', '<b>0.832</b>', '<b>0.854</b>', '<b>0.870</b>', '0.470'],
], [62, 108, 54, 48, 48, 50, 58]))
A(Spacer(1, 6))

A(P('<b>Operating point.</b> The confidence threshold of 0.50 reported in Table&#160;2 was selected '
    'because it is close to count-unbiased on the validation partition: at 0.50 the detector '
    'recovers 96.2&#160;% of annotated instances, whereas at 0.15 it predicts 197 boxes against 157 '
    'true instances, a 25.5&#160;% overcount. Image-level counting error metrics across a threshold '
    'sweep are given in Table&#160;5. Two results bear directly on the recommendations in '
    'Section&#160;5: the threshold that maximises F1 is not the threshold that minimises counting '
    'error, and the optimum differs between partitions — F1 peaks at 0.50 on validation and 0.35 on '
    'test, while count bias crosses zero near 0.45 and 0.30 respectively. Since counting rather than '
    'detection is the task, the count-bias criterion is the operative one.'))
A(Spacer(1, 2))
A(P('<b>Table 5.</b> Image-level counting error against confidence threshold: predicted box count '
    'versus annotated instance count per image. MAE, RMSE and MAPE are reported here, delivering in '
    'the present work the counting-error metrics previously deferred to future study.', 'cap'))
A(tbl([
    ['Partition', 'Preproc.', 'conf', 'F1', 'count MAE', 'RMSE', 'bias', 'MAPE (%)', '&#8721;pred/&#8721;true (%)'],
    ['Validation', 'Raw', '0.15', '0.757', '0.91', '2.06', '+0.61', '32.2', '125.5'],
    ['Validation', 'Raw', '0.35', '0.784', '0.76', '1.71', '+0.15', '23.4', '106.4'],
    ['Validation', 'Raw', '<b>0.50</b>', '<b>0.799</b>', '<b>0.67</b>', '<b>1.58</b>', '<b>&#8722;0.09</b>', '<b>18.1</b>', '<b>96.2</b>'],
    ['Test', 'Raw', '0.35', '<b>0.840</b>', '<b>0.21</b>', '<b>0.51</b>', '&#8722;0.15', '<b>6.8</b>', '91.9'],
    ['Test', 'Raw', '0.50', '0.835', '0.27', '0.66', '&#8722;0.27', '8.1', '85.5'],
    ['Test', 'CLAHE', '0.35', '0.848', '0.38', '0.75', '<b>+0.03</b>', '18.2', '<b>101.6</b>'],
], [58, 46, 32, 38, 52, 40, 42, 48, 66]))
A(Spacer(1, 6))

A(fig(8, '<b>Figure 8.</b> Per-class and overall detection metrics. The juvenile class outperforms the '
    'two smaller classes on every measure; the gap between mAP@0.5 and mAP@0.5:0.95 is wide '
    'throughout, indicating loose box regression rather than outright detection failure.'))

A(P('3.3&#160;&#160;Counting performance', 'h2'))
A(P('Counting results for all nine rounds are given in Table&#160;6 and Fig.&#160;9 shows the live '
    'overlay for each class. Aggregate accuracy was 83.33&#160;% for fingerlings (50 of 60), '
    '87.04&#160;% for post-fingerlings (47 of 54) and 90.48&#160;% for juveniles (38 of 42), giving '
    '86.54&#160;% overall (135 of 156). Round-to-round repeatability was good in every class, with '
    'coefficients of variation between 3.5&#160;% and 4.6&#160;%, indicating that the protocol '
    'itself is stable and that the residual error is a property of the vision system rather than of '
    'inconsistent handling.'))

A(Spacer(1, 2))
A(P('<b>Table 6.</b> Counting performance against the hand-counted reference across three '
    'independent rounds per size class. Within these scored passages all errors were undercounts and '
    'no false positives or double counts were recorded; Section&#160;3.6 reports behaviour outside '
    'this envelope, where both do occur.', 'cap'))
A(tbl([
    ['Class', 'Round', 'Reference', 'Automated', 'Missed', 'Accuracy (%)'],
    ['Fingerling (n = 20)', '1', '20', '17', '3', '85.00'],
    ['', '2', '20', '16', '4', '80.00'],
    ['', '3', '20', '17', '3', '85.00'],
    ['', '<b>Subtotal</b>', '<b>60</b>', '<b>50</b>', '<b>10</b>', '<b>83.33</b>'],
    ['Post-fingerling (n = 18)', '1', '18', '16', '2', '88.89'],
    ['', '2', '18', '15', '3', '83.33'],
    ['', '3', '18', '16', '2', '88.89'],
    ['', '<b>Subtotal</b>', '<b>54</b>', '<b>47</b>', '<b>7</b>', '<b>87.04</b>'],
    ['Juvenile (n = 14)', '1', '14', '13', '1', '92.86'],
    ['', '2', '14', '12', '2', '85.71'],
    ['', '3', '14', '13', '1', '92.86'],
    ['', '<b>Subtotal</b>', '<b>42</b>', '<b>38</b>', '<b>4</b>', '<b>90.48</b>'],
    ['<b>All classes</b>', '<b>9 rounds</b>', '<b>156</b>', '<b>135</b>', '<b>21</b>', '<b>86.54</b>'],
], [112, 62, 62, 62, 50, 66]))
A(Spacer(1, 6))

A(fig(9, '<b>Figure 9.</b> Live inference overlays showing detections, class labels, track identifiers '
    'and the counting line (yellow): (a) fingerlings, (b) post-fingerlings, (c) a juvenile. The '
    'dense, overlapping boxes in (a) illustrate the conditions under which the counting-line logic '
    'is stressed most severely.'))

A(P('3.4&#160;&#160;Agreement with the manual reference', 'h2'))
A(P('Accuracy expressed as a ratio conceals the structure of the error, so the round-level agreement '
    'statistics are reported in Table&#160;7. The automated system undercounted in all nine rounds, '
    'by a mean of 2.33 fish per round (SD 1.00), corresponding to a mean relative undercount of '
    '13.1&#160;% (SD 4.3). The paired t-test rejects equality decisively (t&#160;=&#160;7.00, '
    'df&#160;=&#160;8, p&#160;=&#160;0.00011), and the Bland–Altman limits of agreement (0.37 to '
    '4.29 fish) do not span zero. The error is therefore systematic, not random — an important '
    'finding, because a systematic deficit is amenable to correction by a calibration factor or by '
    'improved detection, whereas random error is not.'))
A(P('The cluster bootstrap over the nine rounds gives 84.1–89.2&#160;%, narrower than the Wilson '
    'interval, because between-round variance is small (round accuracies 85.0, 80.0, 85.0, 88.9, '
    '83.3, 88.9, 92.9, 85.7, 92.9; SD 4.3 percentage points). The Wilson interval is therefore '
    'conservative rather than optimistic in this instance. It remains the case that generalisation '
    'is limited by the nine rounds, not by the 156 passages.'))
A(P('The apparent gradient in accuracy across size classes (Fig.&#160;10a) was not statistically '
    'significant at the sample sizes achieved: the Cochran–Armitage test for trend gave '
    'z&#160;=&#160;1.048 (p&#160;=&#160;0.294) and the chi-square test of homogeneity '
    '&#967;<super>2</super>&#160;=&#160;1.100 (df&#160;=&#160;2, p&#160;=&#160;0.577). The Wilson '
    'confidence intervals overlap substantially across all three classes. The direction of the '
    'effect is nonetheless consistent with the detection metrics, and Fig.&#160;10b shows a strong '
    'but statistically underpowered association between per-class mAP@0.5 and per-class counting '
    'accuracy (r&#160;=&#160;0.943, n&#160;=&#160;3, p&#160;=&#160;0.217). The honest interpretation '
    'is that the size effect is plausible on mechanistic grounds and consistent across two '
    'independent measurement channels, but that this experiment is not powered to establish it.'))

A(Spacer(1, 2))
A(P('<b>Table 7.</b> Round-level agreement between the automated system and the hand-counted '
    'reference (nine rounds).', 'cap'))
A(tbl([
    ['Statistic', 'Value', 'Interpretation'],
    ['Aggregate accuracy', '86.54 % (95 % CI 80.3–91.0)', 'Wilson interval, n = 156 passages'],
    ['Cluster bootstrap over rounds', '84.1–89.2 %', 'Effective unit is the round (n = 9)'],
    ['Fingerling accuracy', '83.33 % (95 % CI 72.0–90.7)', 'Lowest of the three classes'],
    ['Post-fingerling accuracy', '87.04 % (95 % CI 75.6–93.6)', 'Intermediate'],
    ['Juvenile accuracy', '90.48 % (95 % CI 77.9–96.2)', 'Highest of the three classes'],
    ['Mean bias (reference &#8722; automated)', '+2.33 fish per round (SD 1.00)', 'Systematic undercount'],
    ['Mean relative undercount', '13.1 % (SD 4.3)', 'Consistent across rounds'],
    ['Paired t-test', 't = 7.00, df = 8, p = 0.00011', 'Counts are not equivalent'],
    ['Bland–Altman 95 % limits', '+0.37 to +4.29 fish', 'Interval excludes zero'],
    ['Cochran–Armitage trend', 'z = 1.048, p = 0.294', 'Size gradient not significant'],
    ['Chi-square homogeneity', '&#967;<super>2</super> = 1.100, df = 2, p = 0.577', 'Classes not distinguishable'],
], [150, 165, 155]))
A(Spacer(1, 6))

A(fig(10, '<b>Figure 10.</b> (a) Counting accuracy by size class with 95&#160;% Wilson confidence '
    'intervals; the shaded band marks the range commonly reported for manual counting. The intervals '
    'overlap, and the apparent gradient is not statistically significant. (b) Per-class counting '
    'accuracy against per-class validation mAP@0.5; the association is strong in magnitude but rests '
    'on three points.'))

A(P('3.5&#160;&#160;Error taxonomy', 'h2'))
A(P('Frame-by-frame review of the recordings resolved all 21 missed fish into three mechanisms. '
    '<i>Detection misses</i>, in which the fish was visibly present but confidence remained below '
    'the 0.50 threshold, dominated the fingerling class, which sits at the lower edge of what the '
    'model can resolve at 640&#160;×&#160;640 input. <i>Cluster merges</i>, in which two or more '
    'fish crossing together were absorbed into a single bounding box and therefore a single track, '
    'dominated the two larger classes, where greater body area makes overlap more likely and where '
    'the pulsatile movement pattern described in Section&#160;3.1 delivers fish in groups. '
    '<i>Track losses</i>, in which a confirmed track was dropped immediately before the counting '
    'line, were rare in all classes, which retrospectively validates the choice of the lightweight '
    'tracker over DeepSORT for this geometry.'))
A(P('A fourth mechanism, not attributable to any of the above, arises from processing throughput and '
    'is reported here because it is an unquantified contributor to the undercount. Measured '
    'CPU-only on an Intel&#160;i5-6300U (2&#160;cores / 4&#160;threads), the pipeline sustains '
    '5.2&#160;FPS under PyTorch and 7.1&#160;FPS under ONNX Runtime on validation imagery, and '
    '6.7–8.0&#160;FPS on 1080p video, against source footage recorded at 27.6&#160;FPS. At '
    '6&#160;FPS the inter-frame interval is 167&#160;ms, so a fish traversing the counting line '
    'faster than that interval is never observed in two consecutive frames and cannot register a '
    'crossing. The system is therefore real-time on GPU but operates at roughly one quarter of real '
    'time on CPU, and the term &#8220;real-time&#8221; is qualified accordingly throughout.'))
A(P('That the two dominant mechanisms are size-inverted is the practically important result: the '
    'small-fish problem and the large-fish problem require different remedies, and a single global '
    'adjustment of the confidence threshold would improve one at the expense of the other.'))

A(P('3.6&#160;&#160;Behaviour outside the validated envelope', 'h2'))
A(P('The results above were obtained with the camera fixed above the rig and the frame filled by the '
    'observation section. To characterise behaviour outside those conditions, the complete pipeline '
    'was run over two hand-held field recordings of the apparatus (1920&#160;×&#160;1080, 26.8 and '
    '27.6&#160;FPS, 2,294 and 2,815 frames, every frame processed). These clips pan along the pipe '
    'and across surrounding ground; the channel is empty for most of their duration and never holds '
    'more than one or two fish. They are therefore a stress test rather than a validation set, and '
    'they are reported because they expose two failure modes that the controlled rounds cannot.'))
A(P('<b>Configuration sensitivity.</b> Run under a permissive configuration (confidence 0.15, '
    'counting every unique confirmed track irrespective of line crossing or direction), the pipeline '
    'reported 111 and 49 fish on the two clips. Run under the configuration described in '
    'Section&#160;2.5 (confidence 0.50, direction-gated line crossing, minimum three hits), it '
    'reported 2 and 0 against a true content of one to two fish and approximately zero. The counting '
    'rule, not the detector, accounts for the difference: 158 of 160 spurious counts are removed by '
    'the line-crossing and direction gates alone, on identical input and identical weights. '
    'Direction-gated line crossing is thus not merely a de-duplication device, it is the '
    'system&#8217;s principal defence against spurious counts.'))
A(P('<b>Background false positives.</b> Under the permissive configuration a visual audit of all 111 '
    'counted detections on the longer clip found 26 on an actual fish and 85 (77&#160;%) on wet '
    'paving, slab joints, puddles and the outer wall of the pipe. Under the Section&#160;2.5 '
    'configuration the two surviving counts were also inspected individually: neither is a fish. '
    'Both are the turbulent water surface <i>inside</i> the channel, detected as juvenile at '
    'confidence 0.78 and 0.65. This is a materially different finding from out-of-channel '
    'background, and it carries a specific consequence for the hardware recommendation in '
    'Section&#160;5: enclosing the camera so that it views only the channel is necessary but not '
    'sufficient, because the water surface within the channel is itself a false-positive source. Nor '
    'can the threshold be raised to suppress it, since the model assigns empty turbulent water a '
    'higher confidence than it assigns many genuine fingerlings.'))
A(P('The root cause is identified in Section&#160;2.3: the training set contains no background-only '
    'images. All 332 images carry at least one annotated fish, so the model was never presented with '
    'a negative example and has no learned representation of &#8220;not a fish&#8221;. This is the '
    'single highest-return outstanding correction and is placed first among the recommendations.'))
A(P('<b>Class assignment.</b> Re-scoring the permissive run under both class-assignment rules '
    'quantifies the contribution of the majority vote: 26 of 111 counted events (23&#160;%) on the '
    'longer clip, and 3 of 49 (6&#160;%) on the shorter, would have been assigned a different size '
    'class had the label been taken from the final matched frame rather than from the modal label '
    'over the track. Since size sorting <i>is</i> the class assignment, this is a material rather '
    'than cosmetic difference.'))
A(P('Two limits on the interpretation of this section should be stated. First, these clips contain '
    'too few fish to estimate recall; the Section&#160;2.5 configuration counted no genuine fish in '
    'either, which is uninformative given that fish are out of frame for most of the footage, and '
    'must not be read as evidence of poor recall. Second, the direction gate is handicapped here by '
    'camera motion: the pipe is stationary in the world but translates within the frame as the '
    'operator pans, so a stationary false positive can register as a downstream crossing. Under the '
    'fixed-camera geometry of the validation rounds the gate is correspondingly stronger, and this '
    'footage represents a worst case for it.'))

# ============================ 4. DISCUSSION ============================
A(P('4.&#160;&#160;Discussion', 'h1'))

A(P('4.1&#160;&#160;Behaviour as an engineering variable', 'h2'))
A(P('The accuracy achieved here is the joint product of three components, none of which is '
    'sufficient alone: the vision software, the observation geometry that presents fish in a '
    'near-single layer, and the behavioural protocol that induces them to appear at all. The third '
    'is the easiest to overlook and, in this study, was the binding constraint. Detection metrics '
    'evaluate a detector in the abstract; a perfect detector still counts nothing if the population '
    'declines to move. Conversely, a modest nano-scale detector operating on a population that has '
    'been reliably mobilised produces counts of practical value to a hatchery.'))
A(P('The feed-stimulated, flow-assisted protocol is a formalisation of an informal hatchery '
    'practice, and its significance extends beyond counting. Any operation requiring fish to '
    'traverse a channel predictably — grading, vaccination, transfer, harvest — confronts the same '
    'rheotactic obstacle and could employ the same solution. The literature on automated counting '
    'has largely proceeded as though delivery were solved (Zhang et al., 2020; Li et al., 2021; '
    'Gonçalves et al., 2022); the present results suggest that reporting the delivery protocol '
    'should be a standard expectation, in the same way that a wet-lab paper reports its sample '
    'preparation.'))

A(P('4.2&#160;&#160;Where the accuracy is lost, and what would recover it', 'h2'))
A(P('The systematic undercount identified in Section&#160;3.4 is encouraging rather than otherwise, '
    'because its mechanisms are known and individually addressable. Detection misses on small fish '
    'reflect insufficient pixel support at 640&#160;×&#160;640 input combined with a training set of '
    '332 images — both correctable by higher input resolution, small-object-oriented augmentation '
    'and, principally, more data drawn from the operating device rather than from static trays. '
    'There is a domain gap between the training imagery (fish photographed square to the surface in '
    'shallow trays) and the inference imagery (fish in motion through an open channel with surface '
    'disturbance and refraction at the free air–water interface), and closing that gap is likely to '
    'yield a larger return than any architectural change.'))
A(P('Cluster merges on larger fish are a tracking and gating problem rather than a detection '
    'problem. ByteTrack (Zhang et al., 2022), which retains low-confidence detections for a second '
    'association pass instead of discarding them, is well matched to both failure modes and has been '
    'used effectively in exactly this application (Maeda et al., 2026). Replacing the single '
    'counting line with a counting zone bounded by two lines, and requiring track presence in both, '
    'would further reduce the sensitivity to a single ambiguous frame.'))
A(P('The evidence in Section&#160;3.6 reorders these priorities. Neither a better tracker nor a '
    'higher input resolution addresses the absence of negative training examples, which is the '
    'mechanism responsible for the largest observed error magnitudes. Adding background imagery is '
    'also by a wide margin the cheapest of the available interventions.'))

A(P('4.3&#160;&#160;Benchmarking against existing methods', 'h2'))
A(P('Table&#160;8 and Fig.&#160;11 situate the system among manual, semi-automatic, commercial and '
    'research alternatives. Three conclusions follow, and the second and third are less flattering '
    'than the first.'))
A(P('First, on capital cost the system is unmatched: it requires a smartphone the farmer already '
    'owns and a rig assembled from containers and PVC for a few thousand naira, against '
    'USD&#160;3,000–15,000 for commercial optical counters before import costs. Against volumetric '
    'and weight-based estimation — the shortcuts a busy hatchery actually uses when tallying is '
    'impractical — an accuracy of 86.5&#160;% is a clear improvement.'))
A(P('Second, the system does not outperform careful manual tallying of small batches, which the '
    'literature places near 95&#160;% (Li et al., 2021; Zhang et al., 2021). The defensible claim is '
    'narrower and should be stated as such: the system is expected to exceed the accuracy of manual '
    'counting under the conditions where manual counting degrades — large batches, operator fatigue, '
    'poor light — while eliminating the labour and the handling-stress mortality that manual '
    'counting imposes. That expectation is mechanistically motivated but was not tested here, since '
    'the largest round comprised twenty fish. Its advantage is in throughput, repeatability and fish '
    'welfare, not in raw accuracy against a rested operator counting twenty fish.'))
A(P('The cost comparison should be read alongside a throughput comparison, which is less favourable. '
    'A commercial channel counter operates continuously; the present system sustains 5–8&#160;FPS '
    'on CPU hardware of the class a smallholder would own (Section&#160;3.5), which is adequate for '
    'batch processing of recorded video but not for continuous live operation. Capital cost and '
    'throughput are distinct axes and the advantage on the first does not transfer to the second.'))
A(P('Third, the system trails contemporary deep-learning counters by roughly 8–10 percentage points. '
    'Maeda et al. (2026), using YOLOv8 with ByteTrack on a purpose-built capture device, report F1 '
    'above 0.95 and correlation above 0.99 with ground truth; Costa et al. (2022) exceed 99&#160;% '
    'counting a fixed frame of larvae from smartphone images. The comparison must be read with care, '
    'because those tasks differ in difficulty: counting a static frame is materially easier than '
    'line-counting moving fish through a channel, and a purpose-built capture device controls the '
    'lighting and geometry that a hand-held phone does not. Nevertheless the gap is real, and '
    'Section&#160;4.2 identifies its causes. The contribution of this work is not that it is the '
    'most accurate counter, but that it is the most accessible one for which the full delivery '
    'protocol has been reported and validated.'))

A(Spacer(1, 2))
A(P('<b>Table 8.</b> Benchmark comparison across counting approaches. Cost figures are indicative '
    'capital cost, exclusive of import duty, freight and installation, which in Nigeria can double '
    'the landed price of imported equipment.', 'cap'))
A(tbl([
    ['Method', 'Principle', 'Reported accuracy', 'Indicative capital cost'],
    ['Manual direct tally', 'Operator counts individually',
     '~95 % (small batches); degrades with batch size and fatigue', 'Negligible; recurring labour'],
    ['Volumetric estimation', 'Packed volume of a reference sample scaled up', '70–80 %', 'Negligible'],
    ['Weight-based estimation', 'Batch mass ÷ mean individual mass', '80–90 %', 'Balance only'],
    ['Semi-automatic optical / mechanical', 'Narrow channel with light gate or lever', '85–92 %',
     'USD 1,000–2,000'],
    ['Commercial optical counters (AquaScan, Vaki, iAQUA)', 'Channel with optical sensor array',
     '&gt; 95 %', 'USD 3,000–15,000'],
    ['Zhang et al. (2020)', 'U-Net segmentation with hybrid CNN, still images', '~95 %',
     'Laboratory camera rig'],
    ['Costa et al. (2022)', 'Pretrained CNN on smartphone images of larvae', '&#8805; 99 % (static frames)',
     'Smartphone'],
    ['Maeda et al. (2026)', 'YOLOv8 + ByteTrack, purpose-built capture device', 'F1 &gt; 0.95; r &gt; 0.99',
     'Purpose-built device'],
    ['<b>This study</b>', 'YOLOv8n + centroid tracker on smartphone video, feed-stimulated transfer',
     '<b>86.5 % (80.3–91.0)</b>', '<b>Smartphone + ~USD 40–60 rig</b>'],
], [110, 165, 110, 85]))
A(Spacer(1, 6))

A(fig(11, '<b>Figure 11.</b> Reported counting accuracy against indicative capital cost. The system '
    'developed here occupies an otherwise vacant region of the trade-off space — automated and '
    'effectively free of capital cost — but does not reach the accuracy of either capital-intensive '
    'counters or careful small-batch manual tallying.'))

A(P('4.4&#160;&#160;Limitations', 'h2'))
A(P('Seven limitations bound the interpretation of these results, and they are stated in order of '
    'severity rather than of convenience.'))
A(P('<b>(i) Single-session imagery.</b> The entire dataset derives from one 43-minute acquisition '
    'session, and the random split distributes near-simultaneous frames across training, validation '
    'and test partitions (Section&#160;2.3). The detection metrics are consequently within-session '
    'estimates. No claim of cross-session, cross-site or cross-device generalisation is supported by '
    'the present data.'))
A(P('<b>(ii) No negative training examples.</b> The dataset contains no background-only imagery, '
    'with the consequences documented in Section&#160;3.6.'))
A(P('<b>(iii) No comparative baselines.</b> The system was not compared against an alternative '
    'detector, an alternative tracker, or a classical background-subtraction and blob-counting '
    'approach. The accuracy-versus-compute trade-off that would situate the present design is '
    'therefore not established.'))
A(P('<b>(iv) Small test population.</b> Twenty, eighteen and fourteen fish over three rounds each is '
    'sufficient to demonstrate function and estimate accuracy, but not to generalise to commercial '
    'throughput, and explicitly not sufficient to resolve the size gradient statistically. The '
    'effective independent sample is nine rounds.'))
A(P('<b>(v) Narrow operating conditions.</b> Testing was confined to clean water under natural '
    'daylight; performance under turbidity, artificial or failing light, or extended continuous '
    'operation is unknown. Fry below 3&#160;cm were excluded by design.'))
A(P('<b>(vi) Uncharacterised stimulus.</b> Only one feed type was used as the movement stimulus, so '
    'the dose–response relationship of the behavioural protocol remains uncharacterised, as does the '
    'flow regime (Section&#160;2.6).'))
A(P('<b>(vii) Hand-held acquisition.</b> The system was validated as software operated with a '
    'hand-held phone, and the variance introduced by inconsistent camera placement across users has '
    'not been quantified — a limitation that the hardware recommendation in Section&#160;5 is '
    'designed to eliminate.'))

# ============================ 5. CONCLUSIONS ============================
A(P('5.&#160;&#160;Conclusions and Recommendations', 'h1'))
A(P('A smartphone-based computer vision system was developed and validated for counting and '
    'size-sorting <i>Clarias gariepinus</i> fingerlings, combining a YOLOv8n detector fine-tuned on '
    '332 annotated images with a lightweight centroid-association tracker, direction-gated '
    'counting-line logic, majority-vote class assignment and a Flask interface. On the validation '
    'partition the model achieved mAP@0.5&#160;=&#160;0.822 and F1&#160;=&#160;0.797, and on the '
    'held-out test partition mAP@0.5&#160;=&#160;0.832 and F1&#160;=&#160;0.813, both within-session '
    'estimates. Against a hand-counted reference across 156 fish passages the system counted at '
    '86.5&#160;% (95&#160;% CI 80.3–91.0), with accuracy increasing from 83.3&#160;% for fingerlings '
    'to 90.5&#160;% for juveniles, though the gradient did not reach significance at these sample '
    'sizes. Within the scored passages all errors were undercounts, with a systematic bias of 2.33 '
    'fish per round; outside that envelope both false positives and double counts occur, and are '
    'reported in Section&#160;3.6.'))
A(P('The study&#8217;s primary contribution is methodological rather than architectural. Flowing '
    'water alone did not move fingerlings between tanks, because the species orients into the '
    'current; continuous feeding combined with continuous flow moved them reliably. Reporting this '
    'feed-stimulated, flow-assisted protocol closes a gap that published counting systems have '
    'generally left open, and the protocol is transferable to grading, vaccination, transfer and '
    'harvest.'))
A(P('Six recommendations follow directly from the results, ordered by expected return per unit cost.'))
A(P('<b>(i) Add negative training examples.</b> Acquire 30–50 images of the empty rig, the empty '
    'water surface within the channel, and the surrounding ground, annotate them with empty label '
    'files, and retrain. Ultralytics guidance suggests 0–10&#160;% background imagery; at the '
    'present dataset size that is 20–35 negatives. This is the lowest-cost intervention available '
    'and addresses the largest observed error magnitudes (Section&#160;3.6).'))
A(P('<b>(ii) Re-acquire with session-wise splitting.</b> Collect at least one further acquisition '
    'session on a different day, with a different handset and different illumination, and partition '
    'the data <i>by session</i> rather than at random, so that the validation and test partitions '
    'contain no frame from a session represented in training. This converts the within-session '
    'estimates reported here into a generalisation estimate and is a prerequisite for any claim of '
    'transferability.'))
A(P('<b>(iii) Close the domain gap.</b> Acquire 500–1,000 additional annotated frames recorded '
    'through the operating channel rather than in static trays, and fine-tune on that data. This '
    'addresses the dominant fingerling error mode at lower cost than any architectural change.'))
A(P('<b>(iv) Raise input resolution and adopt small-object practice.</b> Train and infer at 960 or '
    '1,280&#160;px rather than 640, add rotation and vertical-flip augmentation (both absent from '
    'the present training run, Section&#160;2.3), and adopt class-specific confidence thresholds — '
    'permissive for fingerlings, stricter for juveniles — since the two dominant error mechanisms '
    'are size-inverted and a single global threshold cannot serve both.'))
A(P('<b>(v) Establish baselines and report uncertainty per count.</b> Compare the present detector '
    'against a larger YOLO variant and against a classical background-subtraction and blob-counting '
    'method, and the present tracker against ByteTrack, reporting accuracy against CPU throughput in '
    'each case. Separately, convert the measured systematic bias into a calibrated prediction '
    'interval, so that a reported count is accompanied by an honest error bound rather than a point '
    'estimate. A count a hatchery can act on is one that states its own uncertainty.'))
A(P('<b>(vi) Package the validated software into a self-contained edge device.</b> The device should '
    'combine an enclosed channel presenting fish in near-single file, an integrated pump delivering '
    'regulated and <i>measured</i> flow, a metered feed dispenser, an embedded inference module and '
    'a local display. Enclosure removes ambient-light variation and inconsistent camera placement — '
    'two uncontrolled variables in the present work — while preserving the cost advantage that '
    'motivates the entire approach. Note from Section&#160;3.6 that enclosure alone does not '
    'eliminate false positives arising from the water surface itself.'))
A(P('Further work should include a systematic feed-stimulus study across pellet size, sinking rate, '
    'composition and dose to convert a qualitatively validated protocol into a quantitatively '
    'optimised one; extension to the fry stage with higher-resolution acquisition; validation at '
    'commercial batch sizes; and multi-species trials on tilapia and <i>Heteroclarias</i> hybrids.'))

# ============================ DECLARATIONS ============================
A(P('Declarations', 'h1'))
A(P('<b>Ethics.</b> All fish were handled under standard hatchery husbandry practice, returned to '
    'holding tanks after each round, and rested between rounds; no mortality occurred during the '
    'trials. Institutional animal-use approval reference: <b>[AUTHOR TO VERIFY: insert approval '
    'reference, or a statement that institutional approval was not required for this class of work '
    'at FUNAAB. Most journals will not proceed without one of the two.]</b>'))
A(P('<b>Data and code availability.</b> Source code, configuration files, trained weights and the '
    'annotated dataset are available at https://github.com/lourish789/fy_fingerling_project. '
    '<b>[AUTHOR TO VERIFY: tag the exact commit used to produce every result in this paper and cite '
    'the tag here. The configuration file in the repository has changed during the course of this '
    'work, and a reader who clones the default branch at a later date will not reproduce these '
    'numbers without the tag.]</b> All detection metrics reported here were computed through the '
    'PyTorch/Ultralytics inference path. The deployed service uses an ONNX Runtime export of the '
    'same weights, which returns 224 detections against the PyTorch path&#8217;s 233 over the 66 '
    'validation images (&#8722;3.9&#160;%; 18 of 66 images differ, maximum per-image difference 2), '
    'owing to letterbox and non-maximum-suppression implementation differences.'))
A(P('<b>Funding.</b> This research received no specific grant from any funding agency.'))
A(P('<b>Conflict of interest.</b> The author declares no competing interests.'))
A(P('<b>Author contributions.</b> <b>[AUTHOR TO VERIFY: if Prof. O.&#160;J. Adeosun is to be named '
    'as co-author, move him from the Acknowledgements to the author list and add a contributions '
    'statement before submission.]</b>'))
A(P('<b>Acknowledgements.</b> The author thanks Prof. O.&#160;J. Adeosun for supervision, and the '
    'academic and technical staff of the Department of Agricultural and Bio-Resources Engineering, '
    'FUNAAB, for facilities and guidance.'))

# ============================ REFERENCES ============================
A(P('References', 'h1'))
REFS = [
 'Adewumi, A. A. (2021). Aquaculture in Nigeria: sustainability issues and challenges. <i>Journal of Fisheries and Aquatic Sciences</i>, 16(1), 1–10.',
 'Arnold, G. P. (1974). Rheotropism in fishes. <i>Biological Reviews</i>, 49(4), 515–576.',
 'Ashley, P. J. (2007). Fish welfare: current issues in aquaculture. <i>Applied Animal Behaviour Science</i>, 104(3–4), 199–235.',
 'Bardach, J. E., Todd, J. H., &amp; Crickmer, R. (1967). Orientation by taste in fish of the genus <i>Ictalurus</i>. <i>Science</i>, 155(3767), 1276–1278.',
 'Barton, B. A. (2002). Stress in fishes: a diversity of responses with particular reference to changes in circulating corticosteroids. <i>Integrative and Comparative Biology</i>, 42(3), 517–525.',
 'Bewley, A., Ge, Z., Ott, L., Ramos, F., &amp; Upcroft, B. (2016). Simple online and realtime tracking. In <i>Proceedings of the IEEE International Conference on Image Processing (ICIP)</i>, 3464–3468.',
 'Bland, J. M., &amp; Altman, D. G. (1986). Statistical methods for assessing agreement between two methods of clinical measurement. <i>The Lancet</i>, 327(8476), 307–310.',
 'Bruton, M. N. (1979). The breeding biology and early development of <i>Clarias gariepinus</i> (Pisces: Clariidae) in Lake Sibaya, South Africa. <i>Transactions of the Zoological Society of London</i>, 35(1), 1–45.',
 'Costa, C. S., Zanoni, V. A. G., Curvo, L. R. V., de Araújo Carvalho, M., Boscolo, W. R., Signor, A., de Arruda, M. S., Nucci, H. H. P., Marcato Junior, J., &amp; Gonçalves, W. N. (2022). Deep learning applied in fish reproduction for counting larvae in images captured by smartphone. <i>Aquacultural Engineering</i>, 97, 102225.',
 'Dwyer, B., Nelson, J., &amp; Solawetz, J. (2023). <i>Roboflow</i> (Version 1.0) [Computer software]. Roboflow, Inc. https://roboflow.com',
 'FAO (2022). <i>The State of World Fisheries and Aquaculture 2022: Towards Blue Transformation</i>. Rome: Food and Agriculture Organization of the United Nations.',
 'França Albuquerque, P. L., Garcia, V., da Silva Oliveira, A., Lewandowski, T., Detweiler, C., Gonçalves, A. B., Costa, C. S., Naka, M. H., &amp; Pistori, H. (2019). Automatic live fingerlings counting using computer vision. <i>Computers and Electronics in Agriculture</i>, 167, 105015.',
 'Garcia, V., Sant&#8217;Ana, D. A., Zanoni, V. A. G., Pache, M. C. B., Naka, M. H., Albuquerque, P. L. F., Lewandowski, T., Oliveira Junior, A. S., Rozales, J. V. A., &amp; Ferreira, M. W. (2020). A new image dataset for the evaluation of automatic fingerlings counting. <i>Aquacultural Engineering</i>, 89, 102064.',
 'Gonçalves, D. N., Acosta, P. R., Ramos, A. P. M., Osco, L. P., Furuya, D. E. G., Furuya, M. T. G., Li, J., Marcato Junior, J., Pistori, H., &amp; Gonçalves, W. N. (2022). Using a convolutional neural network for fingerling counting: a multi-task learning approach. <i>Aquaculture</i>, 557, 738334.',
 'Hara, T. J. (1994). Olfaction and gustation in fish: an overview. <i>Acta Physiologica Scandinavica</i>, 152(2), 207–217.',
 'Jocher, G., Chaurasia, A., &amp; Qiu, J. (2023). <i>Ultralytics YOLOv8</i> [Computer software]. https://github.com/ultralytics/ultralytics',
 'Kasumyan, A. O. (2019). The taste system of fish and the effects of environmental variables. <i>Journal of Ichthyology</i>, 59(1), 1–20.',
 'Li, D., Wang, Z., Wu, S., Miao, Z., Du, L., &amp; Duan, Y. (2021). Automatic counting methods in aquaculture: a review. <i>Journal of the World Aquaculture Society</i>, 52(2), 269–283.',
 'Maeda, V. de A., Sampaio, P. E. F., Bedin, E., Higa, G. T. H., Souza, J. S., Naka, M. H., &amp; Santos, F. M. (2026). Detection, tracking, and counting of <i>Pseudoplatystoma corruscans</i> fingerlings using deep learning and multi-object tracking algorithm. <i>Smart Agricultural Technology</i> (in press).',
 'Montgomery, J. C., Baker, C. F., &amp; Carton, A. G. (1997). The lateral line can mediate rheotaxis in fish. <i>Nature</i>, 389(6654), 960–963.',
 'Redmon, J., Divvala, S., Girshick, R., &amp; Farhadi, A. (2016). You only look once: unified, real-time object detection. In <i>Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition (CVPR)</i>, 779–788.',
 'Ren, S., He, K., Girshick, R., &amp; Sun, J. (2015). Faster R-CNN: towards real-time object detection with region proposal networks. In <i>Advances in Neural Information Processing Systems (NeurIPS)</i>, 91–99.',
 'Saberioon, M., &amp; Císař, P. (2018). Automated within-tank fish mass estimation using infrared reflection system. <i>Computers and Electronics in Agriculture</i>, 150, 484–492.',
 'Saberioon, M., Gómez-Requeni, P., Císař, P., Pautsina, A., &amp; Urban, J. (2017). Application of machine vision systems in aquaculture with emphasis on fish: state-of-the-art and key issues. <i>Reviews in Aquaculture</i>, 9(4), 369–387.',
 'Viveen, W. J. A. R., Richter, C. J. J., van Oordt, P. G. W. J., Janssen, J. A. L., &amp; Huisman, E. A. (1985). <i>Practical Manual for the Culture of the African Catfish (Clarias gariepinus)</i>. The Hague: Directorate General International Cooperation.',
 'Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. <i>Journal of the American Statistical Association</i>, 22(158), 209–212.',
 'Wojke, N., Bewley, A., &amp; Paulus, D. (2017). Simple online and realtime tracking with a deep association metric. In <i>Proceedings of the IEEE International Conference on Image Processing (ICIP)</i>, 3645–3649.',
 'Yang, X., Zhang, S., Liu, J., Gao, Q., Dong, S., &amp; Zhou, C. (2021). Deep learning for smart fish farming: applications, opportunities and challenges. <i>Reviews in Aquaculture</i>, 13(1), 66–90.',
 'Zhang, S., Yang, X., Wang, Y., Zhao, Z., Liu, J., Liu, Y., &amp; Zhou, C. (2020). Automatic fish population counting by machine vision and a hybrid deep neural network model. <i>Animals</i>, 10(2), 364.',
 'Zhang, X., Fu, Z., Cai, W., Tian, D., &amp; Zhang, J. (2021). Applications of computer vision-based image processing in fish counting: a review. <i>Aquaculture Research</i>, 52(1), 1–16.',
 'Zhang, Y., Sun, P., Jiang, Y., Yu, D., Weng, F., Yuan, Z., Luo, P., Liu, W., &amp; Wang, X. (2022). ByteTrack: multi-object tracking by associating every detection box. In <i>Proceedings of the European Conference on Computer Vision (ECCV)</i>, 1–21.',
]
for r in REFS:
    A(P(r, 'ref'))

# ============================ APPENDIX ============================
A(PageBreak())
A(P('Appendix A. Schedule of revisions (delete before submission)', 'h1'))
A(P('This appendix records every substantive change made relative to the previous draft, with the '
    'evidence for each. It is provided for the author&#8217;s review and is not part of the '
    'submitted article.', 'abs'))
A(Spacer(1, 4))
A(tbl([
    ['#', 'Section', 'Previous text', 'Revised to', 'Basis'],
    ['1', 'Abstract, 2.3, Table 1, 4.2, 5', '330 images, balanced 110 per class',
     '332 images, 769 instances, 232/66/34, 51.4/36.2/12.5 % by instance',
     'Counted from the shipped COCO annotation files'],
    ['2', '2.3 (new note), Abstract, 3.2, 4.4(i)', 'No statement on split independence',
     'Single 43-min session; 50 % of val and 59 % of test within 2 s of a train image; metrics '
     'declared within-session',
     'Acquisition timestamps in the image filenames'],
    ['3', '2.4, Table 2', 'GTX 1650, PyTorch 2.0, SGD momentum 0.937, cosine decay, patience 20',
     'Google Colab, Ultralytics 8.4.21, optimizer=auto, linear decay, patience 100',
     'train_args stored in models/best.pt'],
    ['4', '2.4', '3.2 M parameters, 8.7 GFLOPs', '3,011,433 parameters, 8.20 GFLOPs',
     'Those figures are for the 80-class COCO model'],
    ['5', '2.3', 'Eight Roboflow augmentations incl. rotation, vertical flip, blur',
     'Ultralytics on-the-fly defaults; degrees = 0.0 and flipud = 0.0 noted as absent',
     'Checkpoint args; 232 train images = exactly 70 % of 332, so no offline copies exported'],
    ['6', '2.5, Table 2', 'SORT with Kalman filter and IoU association',
     'Hungarian on Euclidean centroid distance, constant-velocity prediction, 160 px gate',
     'No Kalman filter in src/; _compute_iou() defined and never called'],
    ['7', '2.5', 'Per-fish CSV log asserted', 'Both logs described; event log flagged as not yet implemented',
     'CSVLogger writes a per-frame snapshot with no track-id column'],
    ['8', '2.2', '&#8220;Glazed&#8221; / &#8220;transparent observation window&#8221;',
     'Open observation section, free air–water surface', 'Field footage; contradicted the Fig. 1 caption'],
    ['9', '2.2, Eq. (4)', 'A = bh = 0.005 m<super>2</super> (rectangular)',
     'Circular segment, A = 0.00393 m<super>2</super>; conflict with Fig. 1 Detail A flagged',
     'As-built rig is a cut cylindrical pipe; Fig. 1 draws a rectangular flume'],
    ['10', '2.6', '&#8220;Continuous flow at approximately 0.5 L min<super>&#8722;1</super>&#8221;',
     'Throttled discharge described; numeric value flagged BLOCKING for author verification',
     'Inconsistent with head, clearing time and the rheotaxis finding'],
    ['11', 'Table 2, 3.2', 'conf 0.50 cited to config.yaml, which shipped 0.15',
     'conf 0.50 justified by the count-unbiasedness sweep; config corrected in repository',
     'Threshold sweep, Table 5'],
    ['12', 'Table 6 footnote, Abstract, 5', '&#8220;All errors were undercounts; no false positives&#8221;',
     'Narrowed to &#8220;within these scored passages&#8221;, with Section 3.6 added',
     'Audited field footage'],
    ['13', '3.2, Table 3', 'Validation only', 'Held-out test partition added, with instance counts',
     'Previously unreported; present in the repository'],
    ['14', '3.2, Table 4', 'CLAHE not mentioned', 'CLAHE comparison reported; deployment path stated',
     'detect() applies CLAHE unconditionally in production'],
    ['15', '3.2, Table 5', 'MAE/RMSE/MAPE deferred to future work', 'Reported across a threshold sweep',
     'Computable on data already held'],
    ['16', '3.5, 4.3', '&#8220;Real-time&#8221; unqualified', 'Frame-rate-limited misses added as a fourth '
     'error mechanism; 5–8 FPS CPU throughput reported', 'Benchmarked on an i5-6300U'],
    ['17', '3.6 (new)', 'Absent', 'Behaviour outside the validated envelope: 111/49 vs 2/0, 77 % of '
     'permissive counts on background, in-channel water-surface false positives, 23 % of class '
     'assignments altered by the majority vote', 'Full-pipeline runs over both field videos'],
    ['18', '2.8, 3.4', 'Wilson interval only', 'Cluster bootstrap over rounds (84.1–89.2 %) added; '
     'pseudoreplication acknowledged', 'Effective unit is the round, not the passage'],
    ['19', '4.3', '&#8220;The system exceeds manual counting under degraded conditions&#8221;',
     'Reframed as a mechanistically motivated expectation that was not tested',
     'Largest round was 20 fish'],
    ['20', '4.4', 'Five limitations', 'Seven, reordered by severity; leakage, absent negatives and '
     'absent baselines added', '—'],
    ['21', '5', 'Four recommendations', 'Six, reordered by return per unit cost; negatives and '
     'session-wise re-acquisition promoted to first and second', '—'],
    ['22', 'Declarations', 'Repository URL only', 'Commit tag requested; ONNX/PyTorch backend '
     'disparity declared', 'ONNX path returns 3.9 % fewer detections'],
], [16, 72, 108, 130, 108]))

A(Spacer(1, 10))
A(P('Items requiring the author&#8217;s input before submission', 'h2'))
A(P('<b>Blocking.</b> (a) The flow rate and its method of measurement (Section&#160;2.6). '
    '(b) The institutional animal-use approval reference, or a statement that none was required. '
    '(c) A tagged commit corresponding to the reported results.', 'abs'))
A(P('<b>Required but not blocking.</b> (c2) The corresponding author&#8217;s ORCID iD, which was a '
    '&#8220;to be inserted&#8221; placeholder in the first draft and was dropped rather than filled '
    'in the second. (d) The specific Colab accelerator. (e) Whether the per-fish '
    'event log will be implemented or the claim withdrawn. (f) Whether Prof.&#160;Adeosun joins the '
    'author list. (g) Confirmation that the raw round sheets underlying Table&#160;6 are archived '
    'and available, since the Data and Code Availability statement now invites scrutiny of them.', 'abs'))
A(Spacer(1, 8))
A(P('<b>Not addressed by this revision.</b> Three of the requirements commonly applied to this class '
    'of submission remain unmet and cannot be met by editing: comparative baselines against an '
    'alternative detector, tracker and classical method; evaluation across sites, sessions or '
    'devices; and per-count uncertainty quantification. These are recommendations (ii) and (v) in '
    'Section&#160;5 and require new experiments. The present manuscript is an accurate and '
    'defensible account of the work as performed; it is not yet a competitive submission to a '
    'collection that asks for those three things.', 'note'))

doc = SimpleDocTemplate(
    OUT, pagesize=A4,
    leftMargin=20 * mm, rightMargin=20 * mm,
    topMargin=18 * mm, bottomMargin=18 * mm,
    title='Smartphone-Based Counting and Size-Sorting of African Catfish Fingerlings',
    author='Olaiya Flourish Daniel',
    subject='Corrected manuscript draft',
)
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print('WROTE', OUT)
