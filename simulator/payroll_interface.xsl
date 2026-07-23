<?xml version="1.0" encoding="UTF-8"?>
<!-- payroll_interface.xsl: Get_Payroll_Results -> ADP-style PI CSV (your Workday-to-ADP scenario) -->
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wd="urn:com.workday/bsvc" exclude-result-prefixes="env wd">
  <xsl:output method="text"/>
  <xsl:template match="/">
    <xsl:text>EMP_ID,PAY_GROUP,GROSS,ADDL_EARNINGS,BEN_DEDUCTIONS,NET&#10;</xsl:text>
    <xsl:for-each select="//wd:Payroll_Result">
      <xsl:value-of select="concat(wd:Worker_Reference/wd:ID,',',wd:Pay_Group,',',wd:Gross_Amount,',',wd:Additional_Earnings,',',wd:Benefit_Deductions,',',wd:Net_Amount,'&#10;')"/>
    </xsl:for-each>
  </xsl:template>
</xsl:stylesheet>
