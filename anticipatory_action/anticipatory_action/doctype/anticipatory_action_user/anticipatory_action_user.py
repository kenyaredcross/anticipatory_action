# Copyright (c) 2025, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AnticipatoryActionUser(Document):
	def validate(self):
		self.full_name = f'{self.first_name} {self.last_name}'
		self.create_aa_user()


	def create_aa_user (self):
		new_user = frappe.get_doc (
			{
				'doctype': 'User',
				'email': self.email,
				"first_name": self.first_name,
				"last_name": self.last_name,
				"enabled": 1, 
				"role_profile_name": self.role,
				"module_profile": self.role
				

			}
		)

	
		new_user.append('roles', {
			'role': self.role, 
			# 'role_profile': self.role_profile,
			# 'module_profile': self.module_profile		
		})

	
		new_user.insert(ignore_permissions = True)
		