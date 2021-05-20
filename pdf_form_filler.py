import pdfrw


def _text_form(annotation, value):
    pdfstr = pdfrw.objects.pdfstring.PdfString.encode(value)
    annotation.update(pdfrw.PdfDict(V=pdfstr, AS=pdfstr))


def _checkbox(annotation, value, export=None):
    if export:
        export = '/' + export
    else:
        keys = annotation['/AP']['/N'].keys()
        if ['/Off'] in keys:
            keys.remove('/Off')
        export = keys[0]
    if value:
        annotation.update(pdfrw.PdfDict(V=export, AS=export))
    else:
        if '/V' in annotation:
            del annotation['/V']
        if '/AS' in annotation:
            del annotation['/AS']


def _radio_button(annotation, value):
    for each in annotation['/Kids']:
        # determine the export value of each kid
        keys = each['/AP']['/N'].keys()
        if ['/Off'] in keys:
            keys.remove('/Off')
        export = keys[0]

        if f'/{value}' == export:
            val_str = pdfrw.objects.pdfname.BasePdfName(f'/{value}')
        else:
            val_str = pdfrw.objects.pdfname.BasePdfName(f'/Off')
        each.update(pdfrw.PdfDict(AS=val_str))

    annotation.update(pdfrw.PdfDict(V=pdfrw.objects.pdfname.BasePdfName(f'/{value}')))


def _combobox(annotation, value):
    export = None
    for each in annotation['/Opt']:
        if each[1].to_unicode() == value:
            export = each[0].to_unicode()
    if export is None:
        raise KeyError(f"Export Value: {value} Not Found")
    pdfstr = pdfrw.objects.pdfstring.PdfString.encode(export)
    annotation.update(pdfrw.PdfDict(V=pdfstr, AS=pdfstr))


def _listbox(annotation, values):
    pdfstrs = []
    for value in values:
        export = None
        for each in annotation['/Opt']:
            if each[1].to_unicode() == value:
                export = each[0].to_unicode()
        if export is None:
            raise KeyError(f"Export Value: {value} Not Found")
        pdfstrs.append(pdfrw.objects.pdfstring.PdfString.encode(export))
    annotation.update(pdfrw.PdfDict(V=pdfstrs, AS=pdfstrs))


def _field_type(annotation):
    ft = annotation['/FT']
    ff = annotation['/Ff']

    if ft == '/Tx':
        return 'text'
    if ft == '/Ch':
        if ff and int(ff) & 1 << 17:  # test 18th bit
            return 'combo'
        else:
            return 'list'
    if ft == '/Btn':
        if ff and int(ff) & 1 << 15:  # test 16th bit
            return 'radio'
        else:
            return 'checkbox'


def _blank_page(w, h):
    blank = pdfrw.PageMerge()
    blank.mbox = [0, 0, w * 72, h * 72]
    blank = blank.render()
    return blank

def pdf_form_info(in_pdf):
    info = []
    for page in in_pdf.pages:
        annotations = page['/Annots']
        if annotations is None:
            continue
        for annotation in annotations:
            choices=None
            if annotation['/Subtype'] == '/Widget':
                if not annotation['/T']:
                    annotation = annotation['/Parent']
                key = annotation['/T'].to_unicode()
                ft = _field_type(annotation)
                value = annotation['/V']
                if ft =='radio':
                    value = value[1:]
                    choices =[]
                    for each in annotation['/Kids']:
                        keys = each['/AP']['/N'].keys()
                        if not keys[0][1:] in choices:
                            choices.append(keys[0][1:])
                elif ft == 'list' or ft=='combo':
                    choices = [each[1].to_unicode() for each in annotation['/Opt']]
                    values=[]
                    for each in annotation['/Opt']:
                        if each[0] in value:
                            values.append(each[1].to_unicode())
                    value=values
                else:
                    if value:
                        value=value.to_unicode()
                out = dict(name=key, type=ft)
                if value:
                    out['value']=value
                if choices:
                    out['choices']=choices
                info.append(out)
    return info


def fill_form(in_pdf, data, suffix=None):
    fillers = {'checkbox': _checkbox,
               'list': _listbox,
               'text': _text_form,
               'combo': _combobox,
               'radio': _radio_button}
    for page in in_pdf.pages:
        annotations = page['/Annots']
        if annotations is None:
            continue
        for annotation in annotations:

            if annotation['/Subtype'] == '/Widget':
                if not annotation['/T']:
                    annotation=annotation['/Parent']
                key = annotation['/T'].to_unicode()
                if key in data:
                    ft = _field_type(annotation)
                    fillers[ft](annotation, data[key])
                    if suffix:
                        new_T=pdfrw.objects.pdfstring.PdfString.encode(key+suffix)
                        annotation.update(pdfrw.PdfDict(T=new_T))
        in_pdf.Root.AcroForm.update(
            pdfrw.PdfDict(NeedAppearances=pdfrw.PdfObject('true')))
    return in_pdf


def single_form_fill(in_file, data, out_file):
    pdf = pdfrw.PdfReader(in_file)
    out_pdf = fill_form(pdf, data)
    pdfrw.PdfWriter().write(out_file, out_pdf)


def batch_form_fill(template, data, out_file, double_sided=False, splice=-1):
    # deepcopy does not work on PdfDict so we keep the raw inputs
    # so we can may copies of the Pdf structures by reparsing the
    # raw data

    with open(template, 'rb') as f:
        pdf_data = f.read()
    writer = pdfrw.PdfWriter()
    for idx, record in enumerate(data):
        pdf = pdfrw.PdfReader(fdata=pdf_data)  # Create a new instance each time
        out_pdf = fill_form(pdf, record, f'{-idx:04d}')
        if len(out_pdf.pages) % 2 == 1 and double_sided:
            if splice != 0:
                writer.addpages(out_pdf.pages[0:splice])
            writer.addpage(_blank_page(8.5, 11))
            if splice != -1:
                writer.addpages(out_pdf.pages[splice:])
        else:
            writer.addpages(out_pdf.pages)
    writer.trailer.Root.AcroForm = pdfrw.PdfReader(fdata=pdf_data).Root.AcroForm
    writer.trailer.Root.AcroForm.update(pdfrw.PdfDict(NeedAppearances=pdfrw.PdfObject('true')))
    writer.write(out_file)
