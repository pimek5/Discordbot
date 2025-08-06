const { SlashCommandBuilder, EmbedBuilder } = require('discord.js');
const axios = require('axios');

const REGION = 'euw1'; // or na1, based on your player base
const REGIONAL_ROUTING = 'europe'; // use 'americas' for NA/LAN/LAS

module.exports = {
  data: new SlashCommandBuilder()
    .setName('dpm')
    .setDescription('Get DPM stats for a League of Legends summoner.')
    .addStringOption(option =>
      option.setName('summoner')
        .setDescription('Summoner name')
        .setRequired(true)
    ),

  async execute(interaction) {
    const summonerName = interaction.options.getString('summoner');
    await interaction.deferReply();

    try {
      const summonerRes = await axios.get(
        `https://${REGION}.api.riotgames.com/lol/summoner/v4/summoners/by-name/${encodeURIComponent(summonerName)}`,
        { headers: { 'X-Riot-Token': process.env.RIOT_API_KEY } }
      );
      const { puuid } = summonerRes.data;

      const matchListRes = await axios.get(
        `https://${REGIONAL_ROUTING}.api.riotgames.com/lol/match/v5/matches/by-puuid/${puuid}/ids?count=1`,
        { headers: { 'X-Riot-Token': process.env.RIOT_API_KEY } }
      );
      const matchId = matchListRes.data[0];

      const matchRes = await axios.get(
        `https://${REGIONAL_ROUTING}.api.riotgames.com/lol/match/v5/matches/${matchId}`,
        { headers: { 'X-Riot-Token': process.env.RIOT_API_KEY } }
      );

      const match = matchRes.data;
      const player = match.info.participants.find(p => p.puuid === puuid);
      const dpm = (player.totalDamageDealtToChampions / (match.info.gameDuration / 60)).toFixed(1);
      const durationMin = Math.floor(match.info.gameDuration / 60);
      const durationSec = match.info.gameDuration % 60;

      const embed = new EmbedBuilder()
        .setTitle(`${player.summonerName}'s DPM Stats`)
        .setColor('Blurple')
        .addFields(
          { name: 'Champion', value: player.championName, inline: true },
          { name: 'Role', value: player.teamPosition || 'Unknown', inline: true },
          { name: 'KDA', value: `${player.kills}/${player.deaths}/${player.assists}`, inline: true },
          { name: 'DPM', value: dpm, inline: true },
          { name: 'Duration', value: `${durationMin}:${durationSec.toString().padStart(2, '0')}`, inline: true },
          { name: 'Result', value: player.win ? 'Victory' : 'Defeat', inline: true }
        )
        .setFooter({ text: `Match ID: ${matchId}` });

      await interaction.editReply({ embeds: [embed] });

    } catch (err) {
      console.error(err);
      await interaction.editReply(`❌ Could not fetch data for **${summonerName}**. Check the name or try again later.`);
    }
  }
};
