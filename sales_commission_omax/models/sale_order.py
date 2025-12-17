# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, fields


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    commission_analysis_line = fields.One2many('sales.commission.analysis','sale_order_id','Sales Commission')
    salesperson_id = fields.Many2one('res.partner', 'Salesperson', domain="[('is_salesperson', '=', True)]", help="Salesperson assigned to this order for commission purposes.")

    def create_product_commission_analysis_line(self, commission, commission_line, order_lines):
        for line in order_lines:
            order_id = line.order_id
            #Fix Price
            if commission_line.com_with == 'fix_price':
                ####cur
                if commission.currency_id != order_id.currency_id:
                    price_subtotal = order_id.currency_id._convert(line.price_subtotal, commission.currency_id, commission.company_id, order_id.date_order)
                else:
                    price_subtotal = line.price_subtotal
                ####
                price_subtotal_per_qty = price_subtotal/line.product_uom_qty
                if price_subtotal_per_qty >= commission_line.target_price:
                    commission_percentage = commission_line.above_price_commission
                    name = "Product/ (Fix Price) (" + str(commission_percentage) + " %) for Product " + str(line.product_id.name)
                    commission_amount = (price_subtotal * commission_percentage) / 100
                    if commission_amount > 0:#
                        vals = {
                            'name':name,
                            'date':fields.date.today(),
                            'sales_person_id':self.salesperson_id.id,
                            'sale_order_id':self.id,
                            'commission_id':commission.id,
                            'commission_type':commission.commission_type,
                            'product_id':line.product_id.id,
                            'commission_amount':commission_amount
                        }
                        self.env["sales.commission.analysis"].sudo().create(vals)
            #Margin
            if commission_line.com_with == 'margin':
                #ref sale_margin
                purchase_price = self.get_purchase_price(line)
                #############Cur
                if commission.currency_id != order_id.currency_id:
                    purchase_price = order_id.currency_id._convert(purchase_price, commission.currency_id, commission.company_id, order_id.date_order)
                    price_subtotal = order_id.currency_id._convert(line.price_subtotal, commission.currency_id, commission.company_id, order_id.date_order)
                else:
                    price_subtotal = line.price_subtotal
                #############3
                margin = price_subtotal - (purchase_price * line.product_uom_qty)
                #line.margin = line.price_subtotal - (line.purchase_price * line.product_uom_qty)
                margin_percent = (margin/price_subtotal)*100
                ##
                
                if margin_percent >= commission_line.target_margin:
                    commission_percentage = commission_line.above_margin_commission
                    commission_amount = (margin * commission_percentage) / 100
                if margin_percent <= commission_line.target_margin:
                    commission_percentage = commission_line.below_margin_commission
                    commission_amount = (margin * commission_percentage) / 100
                name = "Product/ (Margin Based) (" + str(commission_percentage) + " %) for Product " + str(line.product_id.name)
                if commission_amount > 0:#
                    vals = {
                        'name':name,
                        'date':fields.date.today(),
                        'sales_person_id':self.salesperson_id.id,
                        'sale_order_id':self.id,
                        'commission_id':commission.id,
                        'commission_type':commission.commission_type,
                        'product_id':line.product_id.id,
                        'commission_amount':commission_amount
                    }
                    self.env["sales.commission.analysis"].sudo().create(vals)
            #Commission Exception
            if commission_line.com_with == 'commission_exception':
                commission_percentage = commission_line.commission
                name = "Product/ (Commission Exception) (" + str(commission_percentage) + " %) for Product " + str(line.product_id.name)
                ####cur
                if commission.currency_id != order_id.currency_id:
                    price_subtotal = order_id.currency_id._convert(line.price_subtotal, commission.currency_id, commission.company_id, order_id.date_order)
                else:
                    price_subtotal = line.price_subtotal
                ####
                commission_amount = (price_subtotal * commission_percentage) / 100
                if commission_amount > 0:#
                    vals = {
                        'name':name,
                        'date':fields.date.today(),
                        'sales_person_id':self.salesperson_id.id,
                        'sale_order_id':self.id,
                        'commission_id':commission.id,
                        'commission_type':commission.commission_type,
                        'product_id':line.product_id.id,
                        'commission_amount':commission_amount
                    }
                    self.env["sales.commission.analysis"].sudo().create(vals)

    def create_product_categ_commission_analysis_line(self, commission, commission_line, order_lines):
        for line in order_lines:
            order_id = line.order_id
            #Fix Price
            if commission_line.com_with == 'fix_price':
                ####cur
                if commission.currency_id != order_id.currency_id:
                    price_subtotal = order_id.currency_id._convert(line.price_subtotal, commission.currency_id, commission.company_id, order_id.date_order)
                else:
                    price_subtotal = line.price_subtotal
                ####
                price_subtotal_per_qty = price_subtotal/line.product_uom_qty
                if price_subtotal_per_qty >= commission_line.target_price:
                    commission_percentage = commission_line.above_price_commission
                    #name = "Product/ Product Category/ Margin Based(Fix Price) (" + str(commission_percentage) + " %) for Product " + str(line.product_id.name)
                    name = "Product Category/ (Fix Price) (" + str(commission_percentage) + " %) for Product " + str(line.product_id.name)
                    commission_amount = (price_subtotal * commission_percentage) / 100
                    if commission_amount > 0:#
                        vals = {
                            'name':name,
                            'date':fields.date.today(),
                            'sales_person_id':self.salesperson_id.id,
                            'sale_order_id':self.id,
                            'commission_id':commission.id,
                            'commission_type':commission.commission_type,
                            'product_id':line.product_id.id,
                            'category_id':line.product_id.categ_id.id,#add
                            'commission_amount':commission_amount
                        }
                        self.env["sales.commission.analysis"].sudo().create(vals)
            #Margin
            if commission_line.com_with == 'margin':
                #ref sale_margin
                purchase_price = self.get_purchase_price(line)
                #############Cur
                if commission.currency_id != order_id.currency_id:
                    purchase_price = order_id.currency_id._convert(purchase_price, commission.currency_id, commission.company_id, order_id.date_order)
                    price_subtotal = order_id.currency_id._convert(line.price_subtotal, commission.currency_id, commission.company_id, order_id.date_order)
                else:
                    price_subtotal = line.price_subtotal
                #############3
                margin = price_subtotal - (purchase_price * line.product_uom_qty)
                #line.margin = line.price_subtotal - (line.purchase_price * line.product_uom_qty)
                margin_percent = (margin/price_subtotal)*100
                ##
                
                if margin_percent >= commission_line.target_margin:
                    commission_percentage = commission_line.above_margin_commission
                    commission_amount = (margin * commission_percentage) / 100
                if margin_percent <= commission_line.target_margin:
                    commission_percentage = commission_line.below_margin_commission
                    commission_amount = (margin * commission_percentage) / 100
                name = "Product Category/ (Margin Based) (" + str(commission_percentage) + " %) for Product " + str(line.product_id.name)
                if commission_amount > 0:#
                    vals = {
                        'name':name,
                        'date':fields.date.today(),
                        'sales_person_id':self.salesperson_id.id,
                        'sale_order_id':self.id,
                        'commission_id':commission.id,
                        'commission_type':commission.commission_type,
                        'product_id':line.product_id.id,
                        'category_id':line.product_id.categ_id.id,#add
                        'commission_amount':commission_amount
                    }
                    self.env["sales.commission.analysis"].sudo().create(vals)
            #Commission Exception
            if commission_line.com_with == 'commission_exception':
                commission_percentage = commission_line.commission
                name = "Product Category/ (Commission Exception) (" + str(commission_percentage) + " %) for Product " + str(line.product_id.name)
                ####cur
                if commission.currency_id != order_id.currency_id:
                    price_subtotal = order_id.currency_id._convert(line.price_subtotal, commission.currency_id, commission.company_id, order_id.date_order)
                else:
                    price_subtotal = line.price_subtotal
                ####
                commission_amount = (price_subtotal * commission_percentage) / 100
                if commission_amount > 0:#
                    vals = {
                        'name':name,
                        'date':fields.date.today(),
                        'sales_person_id':self.salesperson_id.id,
                        'sale_order_id':self.id,
                        'commission_id':commission.id,
                        'commission_type':commission.commission_type,
                        'product_id':line.product_id.id,
                        'category_id':line.product_id.categ_id.id,#add
                        'commission_amount':commission_amount
                    }
                    self.env["sales.commission.analysis"].sudo().create(vals)


    def action_confirm(self):#def
        res = super(SaleOrder, self).action_confirm()
        for rec in self:
            commission = self.env["sales.commission"].sudo().search([('company_id','=',self.env.company.id), ('salesperson_ids','in',rec.salesperson_id.id),('start_date','<=',rec.date_order.date()),('end_date','>=',rec.date_order.date()), ('commission_apply_on','=','sale')])
            if commission:
                name = False
                #Standard
                if commission.commission_type == 'standard':
                    for line in rec.order_line.filtered(lambda l: l.display_type == False):
                        name = "Standard Commission (" + str(commission.standard_commission) + " %) for " + str(line.product_id.name)
                        ####cur
                        if commission.currency_id != rec.currency_id:
                            price_subtotal = rec.currency_id._convert(line.price_subtotal, commission.currency_id, commission.company_id, rec.date_order)
                        else:
                            price_subtotal = line.price_subtotal
                        ####
                        commission_amount = (price_subtotal * commission.standard_commission) / 100
                        if commission_amount > 0:#
                            vals = {
                                'name':name,
                                'date':fields.date.today(),
                                'sales_person_id':rec.salesperson_id.id,
                                'sale_order_id':rec.id,
                                'commission_id':commission.id,
                                'commission_type':commission.commission_type,
                                'commission_amount':commission_amount
                            }
                            self.env["sales.commission.analysis"].sudo().create(vals)
                #Partner Based
                if commission.commission_type == 'partner_based':
                    for line in rec.order_line.filtered(lambda l: l.display_type == False):
                        if rec.partner_id.affiliated:
                            commission_percentage = commission.affiliated_partner_commission
                            partner_type = 'Affiliated'
                        else:
                            commission_percentage = commission.non_affiliated_partner_commission
                            partner_type = 'Non Affiliated'
                        
                        name = "Partner Based Commission (" + str(commission_percentage) + " %) for '" + str(partner_type)+ "' " + str(rec.partner_id.name)
                        ####cur
                        if commission.currency_id != rec.currency_id:
                            price_subtotal = rec.currency_id._convert(line.price_subtotal, commission.currency_id, commission.company_id, rec.date_order)
                        else:
                            price_subtotal = line.price_subtotal
                        ####
                        commission_amount = (price_subtotal * commission_percentage) / 100
                        if commission_amount > 0:#
                            vals = {
                                'name':name,
                                'date':fields.date.today(),
                                'sales_person_id':rec.salesperson_id.id,
                                'sale_order_id':rec.id,
                                'commission_id':commission.id,
                                'commission_type':commission.commission_type,
                                'partner_id':rec.partner_id.id,
                                'partner_type':partner_type,
                                'commission_amount':commission_amount
                            }
                            self.env["sales.commission.analysis"].sudo().create(vals)
                #Product/ Product Category/ Margin Based
                if commission.commission_type == 'product_category_margin':
                    for commission_line in commission.sales_commission_line:
                        ###PRODUCT###
                        if commission_line.name == 'product':
                            order_lines = rec.order_line.filtered(lambda l: l.product_id.id == commission_line.product_id.id)
                            rec.create_product_commission_analysis_line(commission, commission_line, order_lines)
                        ###PRODUCT Category###
                        if commission_line.name == 'product_category':
                            order_lines =  rec.order_line.filtered(lambda l: l.product_id.categ_id.id == commission_line.category_id.id)
                            rec.create_product_categ_commission_analysis_line(commission, commission_line, order_lines)
        return res

    def _action_cancel(self):#def
        res = super(SaleOrder, self)._action_cancel()
        for rec in self:
            remove_line = []
            if rec.commission_analysis_line:
                for line in rec.commission_analysis_line:
                    remove_line.append((2, line.id))
                rec.commission_analysis_line = remove_line#remove existing lines
        return res

    def get_purchase_price(self,line):
        line = line.with_company(line.company_id)

        # Convert the cost to the line UoM
        product_cost = line.product_id.uom_id._compute_price(
            line.product_id.standard_price,
            line.product_uom,
        )

        purchase_price = line._convert_to_sol_currency(
            product_cost,
            line.product_id.cost_currency_id)
        return purchase_price
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
