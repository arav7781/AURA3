const fs = require('fs');
const path = require('path');

const outDir = path.join(__dirname, '../out');
const constantsDir = path.join(__dirname, 'src/constants');

if (!fs.existsSync(constantsDir)) {
  fs.mkdirSync(constantsDir, { recursive: true });
}

const extractABI = (contractFile, contractName) => {
  const filePath = path.join(outDir, contractFile, `${contractName}.json`);
  if (fs.existsSync(filePath)) {
    const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    return data.abi;
  }
  return [];
};

const ventureDaoAbi = extractABI('VentureDAO.sol', 'VentureDAO');
const govTokenAbi = extractABI('GovernanceToken.sol', 'GovernanceToken');
const startupContractAbi = extractABI('StartupContract.sol', 'StartupContract');

const fileContent = `
export const VENTUREDAO_ADDRESS = process.env.NEXT_PUBLIC_VENTURADAO_ADDRESS as \`0x\${string}\`;
export const GOVTOKEN_ADDRESS = process.env.NEXT_PUBLIC_GOVTOKEN_ADDRESS as \`0x\${string}\`;

export const VENTUREDAO_ABI = ${JSON.stringify(ventureDaoAbi, null, 2)} as const;

export const GOVTOKEN_ABI = ${JSON.stringify(govTokenAbi, null, 2)} as const;

export const STARTUPCONTRACT_ABI = ${JSON.stringify(startupContractAbi, null, 2)} as const;
`;

fs.writeFileSync(path.join(constantsDir, 'abis.ts'), fileContent.trim() + '\n');
console.log('ABIs extracted successfully to src/constants/abis.ts!');
